import os, json, io
import requests
from bs4 import BeautifulSoup
import boto3
import pandas as pd

# overall script - container?
"""
0. input: call log csv s3 location (do a small one first)
1. get the call log and filter out calls that are > 20 seconds
2. transcribe 2 ways and wait (take job ids into 2 arrays)
3. "while True" loop to check the status of the jobs
3. fetch the outputs
4. analyze the outputs
5. new dataframe, write out to s3 as csv.
"""

# getting mp3 audio
"""
- open the call log
- use the field 'Conference Time (seconds)' to get the duration of the call
- if it's > 20 seconds, then download the audio
- use 'Recording' field to get the URL
- download the audio (2 steps, get html first then get mp3)
- upload the audio to S3
"""

# transcription
"""
- start normal transcriptoin job
- then start post-call canalytics job for Categories and stuff
need the agent to be speaker 0 (can you just assume this because they answer the phone and therefore speak first?)
need the customer to be speaker 1
- wait
"""

# analysis
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

# schema
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
            return save_path
        else:
            print("MP3 URL not found in the HTML.")
    except Exception as e:
        print(f"An error occurred: {e}")


# # Example usage
# original_url = "https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE5f8b4ce0a74338da9a21e7bc0d4720b8"
# save_path = "downloads-new/mp3file.mp3"
# download_mp3_from_html(original_url, save_path)

# call_urls = [
#     'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=REa8fae3124d2512357eeee072724f6ac0',
#     'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE7ddb9736596ff72af3a6e83aadb3f8be',
#     'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=REb6d960d0e8c20f62e95373569fee8f28',
#     'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE5f8b4ce0a74338da9a21e7bc0d4720b8',
#     'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=REe3343dc4545bf88c637c083d555401db',
#     'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=REdb2ef4ebfea7fe431da9deb4c3a9ddcb',
#     'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE5ffa36faa3134bb9b235b00a1fc3a6d4',
#     'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE0c54a5f09c9db90f54844cc6c317e570',
#     'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=REa9306adb927342f34f5d6f5ce52a9beb',
#     'https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE140d7767d0b97cf299c70567499846ae']
#
# for call_url in call_urls:
#     save_path = f"downloads-1/{call_url.split('=')[-1]}.mp3"
#     download_mp3_from_html(call_url, save_path)
#

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

def load_files_from_bucket_and_prefix(bucket, prefix):
    # # use boto3 s3 client to list all files in s3://synergy-sandbox-905418409497/test-transcribe-automation/
    s3 = boto3.client('s3')
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    keys = []
    for obj in response.get('Contents', []):
        keys.append(obj['Key'])
    # now for each key, download the json file and load it into a variable
    # then extract the speaker turns
    objection_scores = []
    for key in keys:
        response = s3.get_object(Bucket=bucket, Key=key)
        data = json.loads(response['Body'].read())
        # Construct transcript turns
        objection_scores.append(data)
    return objection_scores

# read transcript into speaker turns

"""
# Construct transcript turns
transcript_turns = construct_transcript_turns(speech_data)

# Print result
for turn in transcript_turns:
    print(turn)
"""


# bucket_name = 'synergy-sandbox-905418409497'
# object_key = 'sample-data-callerready/Call Log Advanced 4_1 4_15.csv'
def fetch_call_log(bucket_name, object_key):
    s3 = boto3.resource('s3')
    obj = s3.Object(bucket_name, object_key)
    data = obj.get()['Body'].read()
    # put into a df
    df = pd.read_csv(io.BytesIO(data), low_memory=False)
    return df


def get_call_urls(df, duration_threshold=20):
    # filter out calls that are > 20 seconds
    # make list
    filtered_df = df[df['Conference Time (seconds)'] > duration_threshold]
    call_urls = []

    # convert to list
    filtered_df = filtered_df.to_dict('records')

    # get the url, duration, and tracking_guid for this smaller list
    for call_url in filtered_df:
        call_urls.append({
            'url': call_url['Recording'],
            'duration': call_url['Conference Time (seconds)'],
            'tracking_guid': call_url['TrackingGuid'],
        })

    # get the url, duration, and tracking_guid for this smaller list
#     for call_url in filtered_df:
#         call_urls.append({
#             'url': call_url['Recording'],
#             'duration': call_url['Conference Time (seconds)'],
#             'tracking_guid': call_url['TrackingGuid'],
#         })

#     for call_url in filtered_df:
#         print('call_url', call_url)
#         call_urls.append({
#             'url': call_url['Recording'],
#             'duration': call_url['Conference Time (seconds)'],
#             'tracking_guid': call_url['TrackingGuid'],
#         })
    return call_urls


def start_transcription_job(job_name, media_s3_uri, output_bucket, output_key):
    transcribe_client = boto3.client('transcribe', region_name='us-east-1')  # check bucket region
    return transcribe_client.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={
            'MediaFileUri': media_s3_uri
        },
        MediaFormat='mp3',
        OutputBucketName=output_bucket,
        OutputKey=output_key,
        Settings={
            'ShowSpeakerLabels': True,
            'MaxSpeakerLabels': 2,
            'ChannelIdentification': False,
            'ShowAlternatives': False,
        },
        LanguageCode='en-US'
    )
"""
{'TranscriptionJob': {'TranscriptionJobName': 'REe4229b1e1f87f6fde4b5fbced6ba7d2a', 'TranscriptionJobStatus': 'IN_PROGRESS', 'LanguageCode': 'en-US', 'MediaFormat': 'mp3', 'Media': {'MediaFileUri': 's3://synergy-sandbox-us-east-1-905418409497/mp3-downloads/REe4229b1e1f87f6fde4b5fbced6ba7d2a.mp3'}, 'StartTime': datetime.datetime(2024, 5, 16, 17, 1, 51, 7000, tzinfo=tzlocal()), 'CreationTime': datetime.datetime(2024, 5, 16, 17, 1, 50, 979000, tzinfo=tzlocal()), 'Settings': {'ShowSpeakerLabels': True, 'MaxSpeakerLabels': 2, 'ChannelIdentification': False, 'ShowAlternatives': False}}, 'ResponseMetadata': {'RequestId': '5a86a5d7-c1cd-4a5a-aac7-c7149565c4ae', 'HTTPStatusCode': 200, 'HTTPHeaders': {'x-amzn-requestid': '5a86a5d7-c1cd-4a5a-aac7-c7149565c4ae', 'content-type': 'application/x-amz-json-1.1', 'content-length': '463', 'date': 'Thu, 16 May 2024 22:01:50 GMT'}, 'RetryAttempts': 0}}
"""

# automatically flags categories
def start_call_analytics_job(job_name, input_media_uri, output_bucket):
    transcribe_client = boto3.client('transcribe', region_name='us-east-1')  # check bucket region
    return transcribe_client.start_call_analytics_job(
        CallAnalyticsJobName=job_name,
        Settings={
            'LanguageOptions': ['en-US'],
        },
        DataAccessRoleArn='arn:aws:iam::905418409497:role/service-role/AmazonTranscribeServiceRole-my-transcribe-role',
        Media={
            'MediaFileUri': input_media_uri
        },
        OutputLocation=f's3://{output_bucket}/call-analytics-output/analytics-{job_name}.json',
        ChannelDefinitions=[
            {
                'ChannelId': 0,
                'ParticipantRole': 'AGENT'
            },
            {
                'ChannelId': 1,
                'ParticipantRole': 'CUSTOMER'
            }
        ]
    )
"""
{'CallAnalyticsJob': {'CallAnalyticsJobName': 'REe4229b1e1f87f6fde4b5fbced6ba7d2a', 'CallAnalyticsJobStatus': 'IN_PROGRESS', 'Media': {'MediaFileUri': 's3://synergy-sandbox-us-east-1-905418409497/mp3-downloads/REe4229b1e1f87f6fde4b5fbced6ba7d2a.mp3'}, 'StartTime': datetime.datetime(2024, 5, 16, 17, 1, 51, 393000, tzinfo=tzlocal()), 'CreationTime': datetime.datetime(2024, 5, 16, 17, 1, 51, 363000, tzinfo=tzlocal()), 'DataAccessRoleArn': 'arn:aws:iam::905418409497:role/service-role/AmazonTranscribeServiceRole-my-transcribe-role', 'Settings': {'LanguageOptions': ['en-US']}, 'ChannelDefinitions': [{'ChannelId': 0, 'ParticipantRole': 'AGENT'}, {'ChannelId': 1, 'ParticipantRole': 'CUSTOMER'}]}, 'ResponseMetadata': {'RequestId': '71877087-cc17-46a8-beab-a34fa9803b14', 'HTTPStatusCode': 200, 'HTTPHeaders': {'x-amzn-requestid': '71877087-cc17-46a8-beab-a34fa9803b14', 'content-type': 'application/x-amz-json-1.1', 'content-length': '570', 'date': 'Thu, 16 May 2024 22:01:50 GMT'}, 'RetryAttempts': 0}}
"""

#
# # start the transcription job with each key
# job_names = []
# for key in keys:
#     # make the job name just the key without the prefix
#     job_name = key.split('/')[-1].split('.')[0]
#     print(job_name)
#     if len(job_name) > 0:
#         job_names.append(start_transcription_job(
#             f'{job_name}-2',
#             f's3://synergy-sandbox-905418409497/{key}',
#             'synergy-sandbox-905418409497',
#             f'transcription-output/{job_name}-transcription.json'
#         )
#         )
#
# # list transcription jobs
# transcribe = boto3.client('transcribe', region_name='us-east-2')
# response = transcribe.list_transcription_jobs(
#     MaxResults=5,
# )
#
# job_names = []
# while 'NextToken' in response:
#     for job in response['TranscriptionJobSummaries']:
#         job_names.append(job['TranscriptionJobName'])
#     response = transcribe.list_transcription_jobs(
#         NextToken=response['NextToken'],
#     )
#     # if it's the last one, without a NextToken
#     if 'NextToken' not in response:
#         for job in response['TranscriptionJobSummaries']:
#             job_names.append(job['TranscriptionJobName'])
#
# # get the transcription job s3 uri
# s3_uris = []
# for job_name in job_names:
#     transcribe = boto3.client('transcribe', region_name='us-east-2')
#     response = transcribe.get_transcription_job(
#         TranscriptionJobName=job_name
#     )
#     s3_uris.append(response['TranscriptionJob']['Transcript']['TranscriptFileUri'])
#

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
your response should look like this:
[{quote: ..., summary: ..., category: ...}, ...]


Find all the objections the
Find all the turning points in this call. A turning point is a moment in the conversation
where the customer's tone or attitude changes significantly. This could be a moment where the customer
seems to become convinced they want to do it, or a moment where they become convinced they don't want to do it.
List the turning points in an array. For each turning point, state what the customer says that indicates the change
and summarize the sequence of events that led up to the turning point.
"""


def list_objections(conversation_turns):
    prompt = """
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
    """
    # call the llm
    return []


def list_highlights(conversation_turns):
    prompt = """
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
your response should look like an array of json objects like this:
[{"quote": "...", "summary": "...", "category": "..."}, ...]
The response must be json-safe, meaning if you use quotes you should escape them.
JSON:
    """
    # call the llm
    return []


def analyze_post_call_analytics(s3_uri):
    """
    10 for the analytics, just make it a binary on the categories (rapport, and mechanics), --
     % talk and % silence, avg words per minute, num interruptions, overall sentiment, call time
    """
    # download the file from s3, it's a json
    data = download_transcription(s3_uri)

    # ConversationCharacteristics
    duration = data['ConversationCharacteristics']['TotalConversationDurationMillis']
    talk_time = data['ConversationCharacteristics']['TalkTime']['TotalTimeMillis']
    silence_time = data['ConversationCharacteristics']['NonTalkTime']['TotalTimeMillis']
    talk_speed = data['ConversationCharacteristics']['TalkSpeed']['DetailsByParticipant']['AGENT'][
        'AverageWordsPerMinute']
    num_interruptions = data['ConversationCharacteristics']['Interruptions']['TotalCount']
    overall_sentiment = data['ConversationCharacteristics']['Sentiment']['OverallSentiment']['AGENT']

    talk_time_percent = talk_time / duration
    silence_time_percent = silence_time / duration

    # find matched categories if they exist
    categories = data['Categories']['MatchedCategories']  # an array of categories

    # add these to a database
    return {
        'duration': duration,
        'talk_time': talk_time,
        'silence_time': silence_time,
        'talk_speed': talk_speed,
        'num_interruptions': num_interruptions,
        'overall_sentiment': overall_sentiment,
        'talk_time_percent': talk_time_percent,
        'silence_time_percent': silence_time_percent,
        'categories': categories
    }


def get_conversation(s3_uri):
    """
    find objections and classify
    find highlights and classify
    """
    transcript_json = download_transcription(s3_uri)
    # contains each work spoken
    speech_data = transcript_json['results']['items']

    # Construct transcript turns
    conversation = construct_transcript_turns(speech_data)
    return conversation



# overall processing algorithm
"""
1. get the call log
2. get the call urls
3. download the mp3 files
4. start the transcription jobs
5. start the call analytics jobs
6. put both into a queue
7. poll the queue after 5 min
8. download the transcriptions
9. download the analytics
10 for the analytics, just make it a binary on the categories (rapport, and mechanics), -- % talk and % silence, avg words per minute, num interruptions, overall sentiment, call time
11. for the transcriptions,  get the speaker turns then do the analysis
- find objections and classify
- find highlights and classify

FUTURE: write a prompt that describes correct objection handling, and then compare the agent's responses to the correct responses, give them a score.
"""

# mistrla
"""
{
  "modelId": "mistral.mistral-7b-instruct-v0:2",
  "contentType": "application/json",
  "accept": "application/json",
  "body": "{\"prompt\":\"<s>[INST]In Bash, how do I list all text files in the current directory (excluding subdirectories) that have been modified in the last month?[/INST]\",\"max_tokens\":400,\"top_k\":50,\"top_p\":0.7,\"temperature\":0.7}"
}
"""


def invoke_model(prompt):
    bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
    enclosed_prompt = "<s>[INST]" + prompt + "[/INST]"
    body = {
        "prompt": enclosed_prompt,
        "max_tokens": 1000,
    }
    response = bedrock_runtime.invoke_model(
        body=json.dumps(body),
        contentType='application/json',
        accept='application/json',
        modelId='mistral.mistral-7b-instruct-v0:2'
    )
    response_body = json.loads(response["body"].read())
    return response_body
    # resp=invoke_model(prompt)
    # json.loads(resp['outputs'][0]['text'].strip())


### catalog all the objections
"""
get 100 transcriptions
get all objections,
tell the llm to classify them with short phrases like 'not interested', 'too expensive', 'not sure'. And
give it an accepted response.
[{id: ...,
example-objection: ...,
accepted-response: ...,
}]

once they are all classified
"""

return_example=[{
    "id": "is-this-a-scam",
    "example_objection": "I'm not sure if this is real or not",
    "example_response": "We've been in business for 15 years and have been accredited by the better business bureau",
}]

scoring_example=[{
    "id": "legitimacy",
    "example_objection": "I'm not sure if this is real or not",
    "actual_objection": "Is this real?",
    "example_response": "We've been in business for 15 years and have been accredited by the better business bureau",
    "agent_response": "We've been around for a while and have a good reputation",
    "score": 5
}]

def create_prompt(transcript):
    prompt = f"""
{transcript}

---

above is a phone conversation transcript. The agent who received the call is "spk_0".
The customer is "spk_1". The company taking the call offers structured debt services for people
with debts they cannot pay off, such as credit card debt or medical bills. This is a sales call
where the agent seeks to get the customer to commit to the service.
Find all the objections the customer discusses in this call, such as concerns about whether
the offer is legitimate, and whether the credit check will hurt them. List them in an array.
Give each an "id" for classification purposes.
Do not include the agent's objections. Only list those of the customer. Combine similar objections.
For example, if the customer expresses doubt about the sincerity of the offer in two different ways,
combine them into one objection. For each objection, state how the agent handles responds.
If the agent doesn't directly address the objection, state how the agent redirects the conversation.
Return an array of objects like this:
{json.dumps(return_example)}
JSON:
"""
    return prompt

def create_objection_scoring_prompt(library, transcript, scoring_example):
    prompt = f"""
{transcript}

---
objection library:
{json.dumps(library)}
---

above is a phone conversation transcript, followed by an objection library. The agent who received
the call is "spk_0". The customer is "spk_1". The company taking the call offers structured debt services for people
with debts they cannot pay off, such as credit card debt or medical bills. This is a sales call
where the agent seeks to get the customer to commit to the service.
Find all the objections the customer discusses in this call, such as concerns about whether
the offer is legitimate, and whether the credit check will hurt them. Compare them to the list of
accepted objections and responses in the library. For each objection, state how the agent handles responds.
then, give the agent a score based on how well they handled the objection. If the agent's response is
close to the accepted response, give them a score of 10. If the agent's response is the opposite of
the accepted response, give a 0. You can give numbers in between too. Return an array of objects like this:
{json.dumps(scoring_example)}
JSON:
"""
    return prompt


def load_responses(conversations):
    responses = []
    dead_responses=[]
    for conversation in conversations:
        prompt = create_prompt(conversation)
        print(prompt[:200])
        response = invoke_model(prompt)
        try:
            print('model response', response)
            ary = json.loads(response['outputs'][0]['text'].strip())
            for obj in ary:
                responses.append(obj)
        except:
            dead_responses.append(response)
    return responses, dead_responses

def generate_score_responses(conversation, library, scoring_example):
    responses = []
    dead_responses=[]
    p = create_objection_scoring_prompt(library, conversation, scoring_example)
    print(p[:200])
    response = invoke_model(p)
    try:
        ary = json.loads(response['outputs'][0]['text'].strip())
        responses.append(ary)
    except:
        dead_responses.append(response)
    return responses, dead_responses
    #scores, broken_scores=load_score_responses(conversations)

def calculate_objection_score(data):
    total_score = 0
    num_objects = len(data)

    for obj in data:
        total_score += obj['score']

    average_score = total_score / num_objects
    return average_score, num_objects
    # for score in scores:
    #     average_score, num_objections = calculate_objection_score(score)
    #     print('***')
    #     print(f'{num_objections} objections')
    #     print(f'{average_score} avg score')
    #     print('////')