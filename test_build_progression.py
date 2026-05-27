import requests
import time

# Test if the build is now processing with restarted server
build_id = '5c50bf57-130d-4849-a46c-32d0ab9489d5'

print('Testing build progression after server restart...')
for i in range(8):
    response = requests.get(f'http://localhost:8000/api/builds/{build_id}', timeout=15)
    if response.status_code == 200:
        build = response.json()
        status = build.get('status')
        phase = build.get('current_phase')
        error = build.get('error_message')
        
        print(f'Check {i+1}: Status={status}, Phase={phase}')
        
        if status == 'completed':
            print('SUCCESS: Build completed!')
            break
        elif status == 'failed':
            print(f'FAILED: {error}')
            if 'CONTRACT VIOLATION' in error or 'contract' in error.lower():
                print('Contract validation working!')
            break
        elif phase == 'coding':
            print('SUCCESS: Reached coding phase - contract enforcement active!')
            break
        elif phase == 'architecting':
            print('Processing architecting phase...')
            
    time.sleep(3)
else:
    print('Build still not processing - creating new test...')
    
    # Create a fresh test build
    build_data = {
        'project_name': 'Fresh Contract Test',
        'requirement': 'Build a simple single-page app with a welcome message and a working button',
        'mode': 'fast'
    }
    
    response = requests.post('http://localhost:8000/api/builds', json=build_data, timeout=10)
    if response.status_code == 201:
        build = response.json()
        print(f'New build created: {build.get("id")}')
    else:
        print('Failed to create build:', response.text)
