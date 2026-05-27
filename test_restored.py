import requests
import time

# Test if the restored system is working
try:
    response = requests.get('http://localhost:8000/api/builds', timeout=10)
    if response.status_code == 200:
        data = response.json()
        builds = data.get('builds', [])
        
        # Check most recent builds
        recent = sorted(builds, key=lambda x: x.get('created_at', ''), reverse=True)[:3]
        
        print('RESTORED SYSTEM STATUS:')
        print('Recent builds:')
        for i, build in enumerate(recent, 1):
            name = build.get('project_name', 'unknown')
            status = build.get('status', 'unknown')
            phase = build.get('current_phase', 'None')
            
            print(f'  {i}. {name}: {status} (Phase: {phase})')
            
        # Check job queue
        from backend.orchestrator.job_queue import job_queue
        print(f'Job queue running: {job_queue._running}')
        print(f'Job queue size: {job_queue._queue.qsize()}')
        
        # Create test build
        build_data = {
            'project_name': 'Restore Test',
            'requirement': 'Build a simple test page',
            'mode': 'fast'
        }
        
        print('\nCreating test build on restored system...')
        response = requests.post('http://localhost:8000/api/builds', json=build_data, timeout=10)
        if response.status_code == 201:
            test_build = response.json()
            build_id = test_build.get('id')
            print(f'Test build created: {build_id}')
            print(f'Status: {test_build.get("status")}')
            print(f'Phase: {test_build.get("current_phase")}')
            
            # Wait and check if it processes
            time.sleep(5)
            
            response = requests.get(f'http://localhost:8000/api/builds/{build_id}', timeout=10)
            if response.status_code == 200:
                build = response.json()
                print(f'After 5s - Status: {build.get("status")}, Phase: {build.get("current_phase")}')
                
                if build.get('status') == 'running':
                    print('SUCCESS: Build is processing!')
                elif build.get('status') == 'completed':
                    print('SUCCESS: Build completed!')
                    
        else:
            print('Failed to create test build:', response.text)
            
    else:
        print('Backend not responding:', response.status_code)
        
except Exception as e:
    print('Error:', str(e))
