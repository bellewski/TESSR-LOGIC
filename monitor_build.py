import requests
import time

# Monitor the build for a longer period
build_id = 'f226aa79-41a2-4455-ab5f-dac27d4d4249'

print('Long-term monitoring of build:', build_id)
print('Time elapsed | Status | Phase | Notes')
print('-' * 50)

start_time = time.time()

for i in range(12):  # Monitor for 2 minutes
    try:
        response = requests.get(f'http://localhost:8000/api/builds/{build_id}', timeout=15)
        if response.status_code == 200:
            build = response.json()
            status = build.get('status')
            phase = build.get('current_phase')
            retries = build.get('retry_count', 0)
            error = build.get('error_message')
            
            elapsed = int(time.time() - start_time)
            print(f'{elapsed:3d}s      | {status:7s} | {phase or "None":10s} |', end='')
            
            if status == 'completed':
                print('SUCCESS - Build completed!')
                break
            elif status == 'failed':
                print(f'FAILED - {error[:50] if error else "Unknown error"}')
                break
            elif phase == 'architecting' and elapsed > 30:
                print('STUCK - Taking too long in architecting')
            elif phase and phase != 'None':
                print(f'Progressing through {phase}')
            else:
                print('Waiting...')
                
        else:
            print(f'Error checking build: {response.status_code}')
            
    except Exception as e:
        print(f'Error: {str(e)[:30]}')
    
    if i < 11:
        time.sleep(10)  # Wait 10 seconds between checks

print('\nMonitoring complete.')
