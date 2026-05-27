import asyncio
import requests

async def test_queue():
    try:
        from backend.orchestrator.job_queue import job_queue
        print('Queue running:', job_queue._running)
        print('Queue size:', job_queue._queue.qsize())
    except Exception as e:
        print('Queue import error:', e)

    # Create a test build
    build_data = {
        'project_name': 'Queue Test',
        'requirement': 'Build a simple hello world page with HTML, CSS, and JS',
        'mode': 'fast'
    }
    
    print('Creating build...')
    response = requests.post('http://localhost:8000/api/builds', json=build_data, timeout=15)
    
    if response.status_code == 201:
        build = response.json()
        build_id = build.get('id')
        print(f'Build created: {build_id}')
        print(f'Initial status: {build.get("status")}')
        
        # Wait and check status
        await asyncio.sleep(5)
        
        response = requests.get(f'http://localhost:8000/api/builds/{build_id}', timeout=10)
        if response.status_code == 200:
            build = response.json()
            print(f'After 5s - Status: {build.get("status")} | Phase: {build.get("current_phase")}')
        else:
            print('Failed to get build status')
            
    else:
        print('Failed to create build:')
        print(response.text)

asyncio.run(test_queue())
