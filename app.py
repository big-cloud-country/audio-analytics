import boto3
from ProcessingMethods import fetch_call_log, get_call_urls, download_mp3_from_html, start_transcription_job, get_conversation, analyze_post_call_analytics, create_objection_scoring_prompt, start_call_analytics_job, invoke_model, generate_score_responses
import time, os, json
"""

0. input: call log csv s3 location (do a small one first)
1. get the call log and filter out calls that are > 20 seconds
2. transcribe 2 ways and wait (take job ids into 2 arrays)
3. "while True" loop to check the status of the jobs
3. fetch the outputs
4. analyze the outputs
5. new dataframe, write out to s3 as csv.
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

with open('objection-library.json', 'r') as f:
    objection_library = f.read()

def run(
        call_log_bucket,
        call_log_object_key,
        mp3_upload_bucket,
        duration_threshold,
        batch_id):
    #fetch call log csv from s3
    call_log_df = fetch_call_log(call_log_bucket, call_log_object_key)
    call_urls = get_call_urls(call_log_df, duration_threshold)
    transcription_job_ids = []
    call_analytics_job_ids = []
    transcription_job_output_uris = []
    call_analytics_job_output_uris = []
    transcribe = boto3.client('transcribe', region_name='us-east-1')
    for call_url in call_urls:
        save_path = f"mp3-downloads/{call_url['url'].split('=')[-1]}.mp3"
        file_path = download_mp3_from_html(call_url['url'], save_path)
        # upload mp3 file at save_path to s3
        s3 = boto3.client('s3')
        #TODO: partition the key by date
        resp = s3.upload_file(file_path, mp3_upload_bucket, file_path)
        if resp is not None:
            print(f"Failed to upload {file_path} to {call_log_bucket}")
        else:
            print(f"Uploaded {file_path} to {mp3_upload_bucket}")
            # start transcriptoin jobs
            job_name = file_path.split('/')[-1].split('.')[0]
            job_name = f"{job_name}-{batch_id}-{call_url['tracking_guid']}"
            media_s3_uri = f"s3://{mp3_upload_bucket}/{file_path}"
            output_bucket = mp3_upload_bucket
            output_key = f"transcription-outputs/batchid_{batch_id}/{job_name}.json"
            transcription_job_response = start_transcription_job(job_name, media_s3_uri, output_bucket, output_key)
            call_analytics_job_response = start_call_analytics_job(job_name, media_s3_uri, output_bucket)
            transcription_job_ids.append(transcription_job_response['TranscriptionJob']['TranscriptionJobName'])
            call_analytics_job_ids.append(call_analytics_job_response['CallAnalyticsJob']['CallAnalyticsJobName'])
    completed_transcription_jobs = set()
    completed_call_analytics_jobs = set()

    processing_complete = False
    while not processing_complete:
        for job_id in transcription_job_ids:
            if job_id not in completed_transcription_jobs:
                response = transcribe.get_transcription_job(
                    TranscriptionJobName=job_id
                )
                if response['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
                    try:
                        transcription_job_output_uris.append(response['TranscriptionJob']['Transcript']['TranscriptFileUri'])
                    except:
                        print('Transcription job failed')
                    completed_transcription_jobs.add(job_id)

        for job_id in call_analytics_job_ids:
            if job_id not in completed_call_analytics_jobs:
                response = transcribe.get_call_analytics_job(
                    CallAnalyticsJobName=job_id
                )
                if response['CallAnalyticsJob']['CallAnalyticsJobStatus'] in ['COMPLETED', 'FAILED']:
                    try:
                        call_analytics_job_output_uris.append(response['CallAnalyticsJob']['Transcript']['TranscriptFileUri'])
                    except:
                        print('Call analytics job failed')
                    completed_call_analytics_jobs.add(job_id)

        if len(completed_transcription_jobs) == len(transcription_job_ids) and \
           len(completed_call_analytics_jobs) == len(call_analytics_job_ids):
            processing_complete = True
            break

        # Optionally, add a sleep interval to avoid excessive API calls
        time.sleep(10)
        print('Waiting for transcription and call analytics jobs to complete')
    # do something else
    # get the outputs
    process_transcription_outputs(transcription_job_output_uris, call_analytics_job_output_uris, batch_id)
    return

def get_guid_from_uri(uri):
    parts = uri.split("/")
    # Get the last part of the split URL (the file name)
    file_name = parts[-1]
    # Split the file name by "-" and get the parts
    file_name_parts = file_name.split("-")
    # Extract the UUID (the last 5 parts combined)
    uuid_with_extension = "-".join(file_name_parts[-5:])
    # Remove the file extension
    uuid = uuid_with_extension.rsplit(".", 1)[0]
    # Print the extracted UUID
    return uuid


def process_transcription_outputs(
    transcription_job_output_uris,
    call_analytics_job_output_uris,
    batch_id,
    mp3_upload_bucket='synergy-sandbox-us-east-1-905418409497'
    ):
    s3 = boto3.client('s3')
    for transcription_output_uri in transcription_job_output_uris:
        conversation = get_conversation(transcription_output_uri)
        # get the tracking_guid from the uri
        tracking_guid = get_guid_from_uri(transcription_output_uri)
        print('tracking_guid', tracking_guid)
        # run a couple models and prompts
        try:
            responses, dead_responses = generate_score_responses(conversation, objection_library, scoring_example)

            print('Generated responses:', responses)
            print('Generated dead responses:', dead_responses)
            upload_file = {
                "tracking_guid": tracking_guid,
                "responses": responses,
                "dead_responses": dead_responses
            }
            # write json to s3
            object_key = f"objection-scoring/batchid_{batch_id}/{tracking_guid}.json"
            print('Uploading as:', object_key)
            print('Uploading:', upload_file)
            print('Uploading to:', mp3_upload_bucket)
            # instead of upload_file, put_object
            resp = s3.put_object(Body=json.dumps(upload_file), Bucket=mp3_upload_bucket, Key=object_key)
            print('s3 Response:', resp)
        except:
            print('Failed to generate score responses', tracking_guid)
        # attach to a df
    for call_analytics_output_uri in call_analytics_job_output_uris:
        # download the output
        analytics_dict = analyze_post_call_analytics(call_analytics_output_uri)
        tracking_guid = get_guid_from_uri(call_analytics_output_uri)
        # attach this to a df??
        print('Analytics dict:', analytics_dict)
        upload_file = {
            "tracking_guid": tracking_guid,
            "analytics": analytics_dict
        }
        object_key = f"call-analytics-scoring/batchid_{batch_id}/{tracking_guid}.json"
        s3.put_object(Body=json.dumps(upload_file), Bucket=mp3_upload_bucket, Key=object_key)

def get_transcription_outputs(batch_id):
    job_names = []
    transcription_job_output_uris = []
    call_analytics_job_output_uris = []
    transcribe = boto3.client('transcribe', region_name='us-east-1')
    response = transcribe.list_transcription_jobs(MaxResults=5)
    while 'NextToken' in response:
        for job in response['TranscriptionJobSummaries']:
            if batch_id in job['TranscriptionJobName']:
                job_names.append(job['TranscriptionJobName'])
        response = transcribe.list_transcription_jobs(NextToken=response['NextToken'])
        if 'NextToken' not in response:
            for job in response['TranscriptionJobSummaries']:
                if batch_id in job['TranscriptionJobName']:
                    job_names.append(job['TranscriptionJobName'])
    for job_name in job_names:
        response = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        transcription_job_output_uris.append(response['TranscriptionJob']['Transcript']['TranscriptFileUri'])
    response = transcribe.list_call_analytics_jobs(MaxResults=5)
    job_names = []
    while 'NextToken' in response:
        for job in response['CallAnalyticsJobSummaries']:
            if batch_id in job['CallAnalyticsJobName']:
                job_names.append(job['CallAnalyticsJobName'])
        response = transcribe.list_call_analytics_jobs(NextToken=response['NextToken'])
        if 'NextToken' not in response:
            for job in response['CallAnalyticsJobSummaries']:
                if batch_id in job['CallAnalyticsJobName']:
                    job_names.append(job['CallAnalyticsJobName'])
    for job_name in job_names:
        response = transcribe.get_call_analytics_job(CallAnalyticsJobName=job_name)
        call_analytics_job_output_uris.append(response['CallAnalyticsJob']['Transcript']['TranscriptFileUri'])
    return transcription_job_output_uris, call_analytics_job_output_uris

if __name__ == "__main__":
    call_log_bucket='synergy-sandbox-905418409497'
    call_log_object_key='sample-data-callerready/call-log-advanced-50-records.csv'
    mp3_upload_bucket='synergy-sandbox-us-east-1-905418409497'
    duration_threshold=30
    batch_id = 'batch-4'
    transcription_job_output_uris, call_analytics_job_output_uris = get_transcription_outputs(batch_id)
    process_transcription_outputs(transcription_job_output_uris, call_analytics_job_output_uris, batch_id)
#     run(call_log_bucket, call_log_object_key, mp3_upload_bucket, duration_threshold, batch_id)
