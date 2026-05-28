import os
import requests
import time
from tqdm import tqdm

urls = [
    "https://download-r2.pytorch.org/whl/cu124/torch-2.6.0%2Bcu124-cp312-cp312-win_amd64.whl",
    "https://download-r2.pytorch.org/whl/cu124/torchvision-0.21.0%2Bcu124-cp312-cp312-win_amd64.whl",
    "https://download-r2.pytorch.org/whl/cu124/torchaudio-2.6.0%2Bcu124-cp312-cp312-win_amd64.whl"
]

def download_with_resume(url):
    output_file = url.split("/")[-1].replace("%2B", "+")
    
    while True:
        try:
            file_size = 0
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)

            headers = {}
            if file_size > 0:
                headers['Range'] = f'bytes={file_size}-'

            print(f"\nConnecting to download {output_file}... (Resuming from {file_size / (1024**2):.2f} MB)")
            
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            
            if response.status_code == 416:
                print("Download is already 100% complete!")
                break
                
            if response.status_code == 200:
                print("Server did not accept resume. Starting from scratch...")
                file_size = 0
                mode = 'wb'
            elif response.status_code == 206:
                mode = 'ab'
            else:
                print(f"Error {response.status_code}. Retrying in 5 seconds...")
                time.sleep(5)
                continue

            total_size = int(response.headers.get('content-length', 0)) + file_size

            with open(output_file, mode) as f:
                with tqdm(
                    initial=file_size, 
                    total=total_size, 
                    unit='B', 
                    unit_scale=True, 
                    unit_divisor=1024,
                    desc=output_file
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            f.flush()
                            pbar.update(len(chunk))
            
            print(f"\n{output_file} finished successfully!")
            break

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            print(f"\nConnection dropped. Retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"\nUnexpected error: {e}. Retrying in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    for url in urls:
        download_with_resume(url)
