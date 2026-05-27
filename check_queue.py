import requests

# Check job queue status via health endpoint
response = requests.get('http://localhost:8000/api/health', timeout=10)
if response.status_code == 200:
    health = response.json()
    print('Health check:', health)
    
    # Check the new build
    build_id = '7387cc0a-3361-46eb-9181-3e271e7def34'
    build_response = requests.get(f'http://localhost:8000/api/builds/{build_id}', timeout=10)
    if build_response.status_code == 200:
        build = build_response.json()
        print(f'Build {build_id}: Status={build.get("status")}, Phase={build.get("current_phase")}')
else:
    print('Health check failed')
