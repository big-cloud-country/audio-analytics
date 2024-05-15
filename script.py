import os, json, io
import pandas as pd
import requests
from bs4 import BeautifulSoup
import boto3

# getting mp3 audio
"""
- open the call log
- use the field 'Conference Time (seconds)' to get the duration of the call
- if it's > 20 seconds, then download the audio
- use 'Recording' field to get the URL
- download the audio (2 steps, get html first then get mp3)
- upload the audio to S3
"""

#transcription
"""
- start normal transcriptoin job
- then start post-call canalytics job for Categories and stuff
need the agent to be speaker 0 (can you just assume this because they answer the phone and therefore speak first?)
need the customer to be speaker 1
- wait
"""

#analysis
"""
- find out metadata, if the deal was closed or not (call log + zenith)
- download the transcription and assemble the call
- llms: 
-- find turning points - objections, questions, etc
-- find successful points from the sales agent (speaker 0)
-- what are their sources of debt?
"""

# final output
"""
- map unstructured data to structured data, like turning points and objections
- map campaigns & lead sources, to debt sources etc.
"""

# with open('normal-transcription.json') as f:
#     data = json.load(f)
#
# # contains each work spoken
# speech_data = data['results']['items']

#schema
"""
{'type': 'pronunciation', 'alternatives': [{'confidence': '0.999', 'content': 'Thank'}], 'start_time': '3.38', 'end_time': '3.779', 'speaker_label': 'spk_0'}
"""

def get_mp3_url(html_content):
    """
    Parses the HTML content to extract the MP3 URL.
    Args:
        html_content (str): The HTML content as a string.
    Returns:
        str: The MP3 URL if found, otherwise None.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    audio_source = soup.find('source')
    if audio_source and 'src' in audio_source.attrs:
        return audio_source['src']
    return None

def download_mp3_from_html(url, save_path):
    """
    Downloads an MP3 file from a given URL that provides an HTML page with the MP3 resource.
    Args:
        url (str): The URL of the page containing the MP3 resource.
        save_path (str): The path where the MP3 file will be saved.
    """
    try:
        # Get the HTML content
        response = requests.get(url)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        # Parse the HTML to get the MP3 URL
        mp3_url = get_mp3_url(response.text)
        if mp3_url:
            # Download the MP3 file
            mp3_response = requests.get(mp3_url, stream=True)
            mp3_response.raise_for_status()
            # Ensure the save directory exists
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            # Save the MP3 file
            with open(save_path, 'wb') as file:
                for chunk in mp3_response.iter_content(chunk_size=1024):
                    if chunk:
                        file.write(chunk)
            print(f"Downloaded: {save_path}")
        else:
            print("MP3 URL not found in the HTML.")
    except Exception as e:
        print(f"An error occurred: {e}")

# # Example usage
# original_url = "https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE5f8b4ce0a74338da9a21e7bc0d4720b8"
# save_path = "downloads-new/mp3file.mp3"
# download_mp3_from_html(original_url, save_path)

call_urls = ['https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=REa8fae3124d2512357eeee072724f6ac0',
             'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE7ddb9736596ff72af3a6e83aadb3f8be',
             'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=REb6d960d0e8c20f62e95373569fee8f28',
             'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE5f8b4ce0a74338da9a21e7bc0d4720b8',
             'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=REe3343dc4545bf88c637c083d555401db',
             'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=REdb2ef4ebfea7fe431da9deb4c3a9ddcb',
             'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE5ffa36faa3134bb9b235b00a1fc3a6d4',
             'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE0c54a5f09c9db90f54844cc6c317e570',
             'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=REa9306adb927342f34f5d6f5ce52a9beb',
             'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE140d7767d0b97cf299c70567499846ae']

for call_url in call_urls:
    save_path = f"downloads-1/{call_url.split('=')[-1]}.mp3"
    download_mp3_from_html(call_url, save_path)


# use boto3 s3 client to list all files in s3://synergy-sandbox-905418409497/test-transcribe-automation/
s3=boto3.client('s3')
response = s3.list_objects_v2(Bucket='synergy-sandbox-905418409497', Prefix='test-transcribe-automation/')
keys = []
for obj in response.get('Contents', []):
    keys.append(obj['Key'])

#read transcript into speaker turns
def construct_transcript_turns(speech_data):
    """
    need to pass in transcript_json['results']['items']
    """
    turns = []
    current_speaker = None
    current_content = []
    for item in speech_data:
        speaker = item['speaker_label']
        word = item['alternatives'][0]['content']
        if speaker != current_speaker:
            if current_speaker is not None:
                turns.append({'speaker': current_speaker, 'content': ' '.join(current_content)})
            current_speaker = speaker
            current_content = [word]
        else:
            current_content.append(word)
    # Add the last turn
    if current_speaker is not None:
        turns.append({'speaker': current_speaker, 'content': ' '.join(current_content)})
    return turns

"""
# Construct transcript turns
transcript_turns = construct_transcript_turns(speech_data)

# Print result
for turn in transcript_turns:
    print(turn)
"""
def fetch_call_log():
    s3 = boto3.resource('s3')
    bucket_name = 'synergy-sandbox-905418409497'
    object_key = 'sample-data-callerready/Call Log Advanced 4_1 4_15.csv'
    obj = s3.Object(bucket_name, object_key)
    data = obj.get()['Body'].read()
    # put into a df
    df = pd.read_csv(io.BytesIO(data), low_memory=False)
    return df

def get_call_urls(df):
    # filter out calls that are > 20 seconds
    # make list
    call_urls = []
    for call_url in df[df['Conference Time (seconds)'] > 20]['Recording']:
        call_urls.append(call_url)
    return call_urls
def start_transcription_job(job_name, media_s3_uri, output_bucket, output_key):
    transcribe_client=boto3.client('transcribe', region_name='us-east-2') #check bucket region
    return transcribe_client.start_transcription_job(
        TranscriptionJobName = job_name,
        Media = {
            'MediaFileUri': media_s3_uri
        },
        MediaFormat = 'mp3',
        OutputBucketName = output_bucket,
        OutputKey = output_key,
        Settings={
            'ShowSpeakerLabels': True,
            'MaxSpeakerLabels': 2,
            'ChannelIdentification': False,
            'ShowAlternatives': False,
            'MaxAlternatives': 1
        },
        LanguageCode = 'en-US'
    )

def start_call_analytics_job(job_name, transcription_job_name, output_bucket):
    transcribe_client=boto3.client('transcribe', region_name='us-east-2') #check bucket region
    return transcribe_client.start_call_analytics_job(
        CallAnalyticsJobName = job_name,
        Media = {
            'MediaFileUri': f's3://{output_bucket}/transcription-output/{transcription_job_name}.json'
            },
        OutputLocation =  f's3://{output_bucket}/call-analytics-output/analytics-{transcription_job_name}.json',
    )

# start the transcription job with each key
job_names=[]
for key in keys:
    #make the job name just the key without the prefix
    job_name = key.split('/')[-1].split('.')[0]
    print(job_name)
    if len(job_name) > 0:
        job_names.append(start_transcription_job(
            f'{job_name}-2',
            f's3://synergy-sandbox-905418409497/{key}',
            'synergy-sandbox-905418409497',
            f'transcription-output/{job_name}-transcription.json'
        )
        )

#list transcription jobs
transcribe=boto3.client('transcribe', region_name='us-east-2')
response = transcribe.list_transcription_jobs(
    MaxResults=5,
)

job_names = []
while 'NextToken' in response:
    for job in response['TranscriptionJobSummaries']:
        job_names.append(job['TranscriptionJobName'])
    response = transcribe.list_transcription_jobs(
        NextToken=response['NextToken'],
    )
    # if it's the last one, without a NextToken
    if 'NextToken' not in response:
        for job in response['TranscriptionJobSummaries']:
            job_names.append(job['TranscriptionJobName'])

# get the transcription job s3 uri
s3_uris=[]
for job_name in job_names:
    transcribe=boto3.client('transcribe', region_name='us-east-2')
    response = transcribe.get_transcription_job(
        TranscriptionJobName=job_name
    )
    s3_uris.append(response['TranscriptionJob']['Transcript']['TranscriptFileUri'])

# json file at an s3 uri. download it

def download_transcription(s3_uri):
    s3 = boto3.client('s3', region_name='us-east-2')
    bucket = s3_uri.split('/')[3]
    key = '/'.join(s3_uri.split('/')[4:])
    response = s3.get_object(Bucket=bucket, Key=key)
    data = response['Body'].read()
    return json.loads(data)

### analysis
"""
prompts

to find objections

1
above is a phone conversation transcript. The agent who received the call is "spk_0". 
A customer is "spk_1". The company taking the call offers structured debt services for people 
with debts they cannot pay off, such as credit card debt or medical bills. This is a sales call. 
Find all the objections the customer discusses in this call. List them in an array.

2
above is a phone conversation transcript. The agent who received the call is "spk_0". 
A customer is "spk_1". The company taking the call offers structured debt services for people 
with debts they cannot pay off, such as credit card debt or medical bills. This is a sales call. 
Find all the objections the customer discusses in this call, such as concerns about whether 
the offer is legitimate, and whether the credit check will hurt them. List them in an array.
Do not include the agent's objections, only those of the customer.

3
above is a phone conversation transcript. The agent who received the call is "spk_0". 
The customer is "spk_1". The company taking the call offers structured debt services for people 
with debts they cannot pay off, such as credit card debt or medical bills. This is a sales call 
where the agent seeks to get the customer to commit to the service.
Find all the objections the customer discusses in this call, such as concerns about whether 
the offer is legitimate, and whether the credit check will hurt them. List them in an array.
Do not include the agent's objections. Only list those of the customer. Combine similar objections.
For example, if the customer expresses doubt about the sincerity of the offer in two different ways,
combine them into one objection. For each objection, state how the agent handles responds. 
If the agent doesn't directly address the objection, state how the agent redirects the conversation. 
Return a response like this:
[{objection: ..., response: ...}, ...]


list and categorize highlights
above is a phone conversation transcript. The agent who received the call is "spk_0". 
The customer is "spk_1". The company taking the call offers structured debt services for people 
with debts they cannot pay off, such as credit card debt or medical bills. This is a sales call 
where the agent seeks to get the customer to commit to the service. 
Find up to 10 highlights of the call. A highlight is a moment in the conversation where the agent
successfully handles an objection or concern of the customer, or where the agent successfully convinces
the customer to commit to the service, or where the agent clearly explains the service in a way that
the customer seems to understand. List the highlights in an array. For each highlight, quote the part of 
the transcript that you are highlighting, summarize the highlight, and categorize it as one of the following:
- objection_handled
- customer_convinced
- positive_rapport
- de_escalation
- service_explained
- other


Find all the objections the
Find all the turning points in this call. A turning point is a moment in the conversation
where the customer's tone or attitude changes significantly. This could be a moment where the customer
seems to become convinced they want to do it, or a moment where they become convinced they don't want to do it.
List the turning points in an array. For each turning point, state what the customer says that indicates the change
and summarize the sequence of events that led up to the turning point.
"""