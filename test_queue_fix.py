import requests
import time

# Create a test build to trigger the queue
build_data = {
    'project_name': 'Queue Fix Test',
    'requirement': 'Build a simple test page with HTML, CSS, and JS',
    'mode': 'fast'
}

print('Creating test build to trigger queue...')
response = requests.post('http://localhost:8000/api/builds', json=build_data, timeout=10)
if response.status_code == 201:
    build = response.json()
    build_id = build.get('id')
    print(f'Build created: {build_id}')
    
    # Check if queue starts automatically
    time.sleep(2)
    
    from backend.orchestrator.job_queue import job_queue
    print('Queue running after build creation:', job_queue._running)
    print('Queue size:', job_queue._queue.qsize())
    
    # Check build status
    response = requests.get(f'http://localhost:8000/api/builds/{build_id}', timeout=10)
    if response.status_code == 200:
        build = response.json()
        print('Build status:', build.get('status'))
        print('Build phase:', build.get('current_phase'))
        
        # Wait a bit more to see if it processes
        time.sleep(5)
        response = requests.get(f'http://localhost:8000/api/builds/{build_id}', timeout=10)
        if response.status_code == 200:
            build = response.json()
            print('Build status after 5s:', build.get('status'))
            print('Build phase after 5s:', build.get('current_phase'))
else:
    print('Failed to create build:', response.text)
