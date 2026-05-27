import requests

# Check the current build status
build_id = '576a1ace-b873-4a7c-8f9e-9b85e9ded244'
response = requests.get(f'http://localhost:8000/api/builds/{build_id}', timeout=10)
if response.status_code == 200:
    build = response.json()
    print(f'Build Status: {build.get("status")}')
    print(f'Current Phase: {build.get("current_phase")}')
    print(f'Error Message: {build.get("error_message", "None")}')
    
    # Get recent events to see what's happening
    events_response = requests.get(f'http://localhost:8000/api/builds/{build_id}/events', timeout=10)
    if events_response.status_code == 200:
        events = events_response.json().get('events', [])
        print(f'\nRecent Events (last 5):')
        for event in events[-5:]:
            print(f'  - {event.get("event_type")}: {event.get("message", "")}')
else:
    print('Failed to get build status')
