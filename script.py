import os, json
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

with open('normal-transcription.json') as f:
    data = json.load(f)

# contains each work spoken
speech_data = data['results']['items']

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

# Example usage
original_url = "https://admins.callerready.com/Recordings/Recording?AccountSid=AC3951a31053e8b50054f86fa930d61eb6&RecordingSid=RE5f8b4ce0a74338da9a21e7bc0d4720b8"
save_path = "downloads-new/mp3file.mp3"
download_mp3_from_html(original_url, save_path)

#read transcript into speaker turns
def construct_transcript_turns(speech_data):
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

def start_transcription_job(job_name, media_s3_uri, output_bucket, output_key):
    transcribe_client=boto3.client('transcribe', region_name='us-east-1') #check bucket region
    transcribe_client.start_transcription_job(
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