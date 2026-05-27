import requests

# Test if the restored system is working
try:
    response = requests.get('http://localhost:8000/api/builds', timeout=10)
    if response.status_code == 200:
        data = response.json()
        builds = data.get('builds', [])
        
        # Check most recent builds
        recent = sorted(builds, key=lambda x: x.get('created_at', ''), reverse=True)[:3]
        
        print('System Status Check:')
        print('Recent builds:')
        for i, build in enumerate(recent, 1):
            name = build.get('project_name', 'unknown')
            status = build.get('status', 'unknown')
            phase = build.get('current_phase', 'None')
            
            print(f'  {i}. {name}: {status} (Phase: {phase})')
            
        # Create a simple test build
        build_data = {
            'project_name': 'System Restore Test',
            'requirement': 'Build a simple test page',
            'mode': 'fast'
        }
        
        print('\nCreating test build...')
        response = requests.post('http://localhost:8000/api/builds', json=build_data, timeout=10)
        if response.status_code == 201:
            test_build = response.json()
            build_id = test_build.get('id')
            print(f'Test build created: {build_id}')
            print(f'Status: {test_build.get("status")}')
            print(f'Phase: {test_build.get("current_phase")}')
            
            # Wait a moment to see if it processes
            import time
            time.sleep(3)
            
            response = requests.get(f'http://localhost:8000/api/builds/{build_id}', timeout=10)
            if response.status_code == 200:
                build = response.json()
                print(f'After 3s - Status: {build.get("status")}, Phase: {build.get("current_phase")}')
        else:
            print('Failed to create test build:', response.text)
            
    else:
        print('Backend not responding:', response.status_code)
        
except Exception as e:
    print('Error:', str(e))
