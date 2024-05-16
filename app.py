import boto3
from ProcessingMethods import fetch_call_log, get_call_urls, download_mp3_from_html, start_transcription_job, start_call_analytics_job

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
        duration_threshold):
    #fetch call log csv from s3
    call_log_df = fetch_call_log(call_log_bucket, call_log_object_key)
    call_urls = get_call_urls(call_log_df, duration_threshold)
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
            media_s3_uri = f"s3://{mp3_upload_bucket}/{file_path}"
            output_bucket = mp3_upload_bucket
            output_key = f"transcription-outputs/{job_name}.json"
            transcription_job_id = start_transcription_job(job_name, media_s3_uri, output_bucket, output_key)
            call_analytics_job_id = start_call_analytics_job(job_name, media_s3_uri, output_bucket)
    return


if __name__ == "__main__":
    call_log_bucket='synergy-sandbox-905418409497'
    call_log_object_key='sample-data-callerready/call-log-advanced-50-records.csv'
    mp3_upload_bucket='synergy-sandbox-us-east-1-905418409497'
    duration_threshold=30
    run()