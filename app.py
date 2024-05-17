import boto3
from ProcessingMethods import fetch_call_log, get_call_urls, download_mp3_from_html, start_transcription_job, get_conversation, analyze_post_call_analytics, start_call_analytics_job
import time
"""

0. input: call log csv s3 location (do a small one first)
1. get the call log and filter out calls that are > 20 seconds
2. transcribe 2 ways and wait (take job ids into 2 arrays)
3. "while True" loop to check the status of the jobs
3. fetch the outputs
4. analyze the outputs
5. new dataframe, write out to s3 as csv.
"""

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
        save_path = f"mp3-downloads/{call_url.split('=')[-1]}.mp3"
        file_path = download_mp3_from_html(call_url, save_path)
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
            job_name = f'{job_name}-{batch_id}'
            media_s3_uri = f"s3://{mp3_upload_bucket}/{file_path}"
            output_bucket = mp3_upload_bucket
            output_key = f"transcription-outputs/{job_name}.json"
            transcription_job_response = start_transcription_job(job_name, media_s3_uri, output_bucket, output_key)
            call_analytics_job_response = start_call_analytics_job(job_name, media_s3_uri, output_bucket)
            transcription_job_ids.append(transcription_job_response['TranscriptionJob']['TranscriptionJobName'])
            call_analytics_job_ids.append(call_analytics_job_response['CallAnalyticsJob']['CallAnalyticsJobName'])
    completed_transcription_jobs = set()
    completed_call_analytics_jobs = set()

    while True:
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
            break

        # Optionally, add a sleep interval to avoid excessive API calls
        time.sleep(10)
        print('Waiting for transcription and call analytics jobs to complete')
    # do something else
    # get the outputs
    for transcription_output_uri in transcription_job_output_uris:
        conversation = get_conversation(transcription_output_uri)
        # run a couple models and prompts
        # build out the scores
        # attach to a df.
        pass
    for call_analytics_output_uri in call_analytics_job_output_uris:
        # download the output
        analytics_dict = analyze_post_call_analytics(call_analytics_output_uri)
        # attach this to a df??
        pass
    return


if __name__ == "__main__":
    call_log_bucket='synergy-sandbox-905418409497'
    call_log_object_key='sample-data-callerready/call-log-advanced-50-records.csv'
    mp3_upload_bucket='synergy-sandbox-us-east-1-905418409497'
    duration_threshold=30
    batch_id = 'batch-2'
    run(call_log_bucket, call_log_object_key, mp3_upload_bucket, duration_threshold, batch_id)