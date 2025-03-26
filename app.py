import os
import re
import requests
import json
import concurrent.futures
import io
import zipfile
from dotenv import load_dotenv
from flask import Flask, request, render_template, flash, redirect, url_for, send_file
from flask_session import Session

# Load environment variables from .env file
load_dotenv()
ASANA_ACCESS_TOKEN = os.getenv('ASANA_ACCESS_TOKEN')
WORKSPACE_ID = os.getenv('WORKSPACE_GID')

if not ASANA_ACCESS_TOKEN or not WORKSPACE_ID:
    raise Exception("Please set ASANA_ACCESS_TOKEN and WORKSPACE_GID in your .env file.")

# Flask app setup
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
Session(app)

# Asana API configuration
headers = {
    'Authorization': f'Bearer {ASANA_ACCESS_TOKEN}',
    'Accept': 'application/json'
}
BASE_URL = "https://app.asana.com/api/1.0"
MAX_PATH_LENGTH = 200  # Maximum allowed length for any file or folder path

def safe_filename(filename):
    """Convert filename to a safe version by replacing unwanted characters."""
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)

def limit_path(path, max_length=MAX_PATH_LENGTH):
    """Ensure the given file path does not exceed max_length characters."""
    if len(path) <= max_length:
        return path
    directory, filename = os.path.split(path)
    allowed = max_length - len(directory) - 1  # reserve 1 for os.sep
    if allowed <= 0:
        return path[:max_length]
    name, ext = os.path.splitext(filename)
    allowed_name_length = allowed - len(ext)
    if allowed_name_length < 1:
        truncated_filename = filename[:allowed]
    else:
        truncated_filename = name[:allowed_name_length] + ext
    return os.path.join(directory, truncated_filename)

def construct_project_folder(output_dir, project_name, project_gid, max_length=MAX_PATH_LENGTH):
    """Construct a folder name for the project and ensure it does not exceed max_length."""
    safe_name = safe_filename(project_name)
    folder_name = f"{safe_name}_{project_gid}"
    full_path = os.path.join(output_dir, folder_name)
    return limit_path(full_path, max_length)

def get_projects():
    """
    Fetch all projects in the specified workspace using pagination.
    Include the 'team' and 'name' fields using the opt_fields parameter.
    """
    projects = []
    params = {"limit": 100, "opt_fields": "team,name"}
    url = f"{BASE_URL}/workspaces/{WORKSPACE_ID}/projects"
    while url:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            projects.extend(data.get('data', []))
            next_page = data.get("next_page", None)
            if next_page and next_page.get("offset"):
                params["offset"] = next_page["offset"]
            else:
                url = None
        else:
            print("Error fetching projects:", response.text)
            break
    return projects

def get_teams():
    """
    Fetch all teams for the authenticated user filtered by the given workspace.
    Uses the GET /users/me/teams endpoint.
    """
    teams = []
    params = {"limit": 100, "workspace": WORKSPACE_ID}
    url = f"{BASE_URL}/users/me/teams"
    while url:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            teams.extend(data.get('data', []))
            next_page = data.get("next_page", None)
            if next_page and next_page.get("offset"):
                params["offset"] = next_page["offset"]
            else:
                url = None
        else:
            print("Error fetching teams:", response.text)
            break
    return teams

def get_team_details(team_gid):
    """Fetch team details for a given team gid."""
    url = f"{BASE_URL}/teams/{team_gid}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('data', {})
    else:
        print(f"Error fetching team details for {team_gid}:", response.text)
        return {}

# Other helper functions remain unchanged.
def get_project_details(project_gid):
    url = f"{BASE_URL}/projects/{project_gid}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('data', {})
    else:
        print(f"Error fetching project details for {project_gid}:", response.text)
        return {}

def get_project_tasks(project_gid):
    url = f"{BASE_URL}/projects/{project_gid}/tasks"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('data', [])
    else:
        print(f"Error fetching tasks for project {project_gid}:", response.text)
        return []

def get_task_details(task_gid):
    url = f"{BASE_URL}/tasks/{task_gid}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('data', {})
    else:
        print(f"Error fetching task details for {task_gid}:", response.text)
        return {}

def get_task_subtasks(task_gid):
    url = f"{BASE_URL}/tasks/{task_gid}/subtasks"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('data', [])
    else:
        print(f"Error fetching subtasks for task {task_gid}:", response.text)
        return []

def get_task_stories(task_gid):
    url = f"{BASE_URL}/tasks/{task_gid}/stories"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('data', [])
    else:
        print(f"Error fetching stories for task {task_gid}:", response.text)
        return []

def get_task_attachments(task_gid):
    url = f"{BASE_URL}/tasks/{task_gid}/attachments"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('data', [])
    else:
        print(f"Error fetching attachments for task {task_gid}:", response.text)
        return []

def get_attachment_details(attachment_gid):
    url = f"{BASE_URL}/attachments/{attachment_gid}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('data', {})
    else:
        print(f"Error fetching attachment details for {attachment_gid}: {response.text}")
        return {}

def download_attachment(attachment_details, save_dir, task_gid):
    download_url = attachment_details.get("download_url")
    if not download_url:
        print(f"No download URL for attachment {attachment_details.get('gid')}")
        return None

    original_name = attachment_details.get("name", f"attachment_{attachment_details.get('gid')}")
    file_name = safe_filename(f"task_{task_gid}_{original_name}")
    file_path = os.path.join(save_dir, file_name)
    file_path = limit_path(file_path, MAX_PATH_LENGTH)
    
    try:
        response = requests.get(download_url, stream=True)
        if response.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Downloaded attachment: {file_name}")
            return file_path
        else:
            print(f"Failed to download attachment {attachment_details.get('gid')}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Exception downloading attachment {attachment_details.get('gid')}: {e}")
        return None

def export_project(project, project_dir=None):
    """
    Export all available data for a project.
    If project_dir is provided, attachments will be downloaded to disk.
    If project_dir is None, attachments are not downloaded.
    Returns a dict of project data.
    """
    project_gid = project['gid']
    project_data = {"project_details": get_project_details(project_gid)}
    tasks = get_project_tasks(project_gid)
    project_tasks = []
    
    for task in tasks:
        task_gid = task['gid']
        task_info = get_task_details(task_gid)
        subtasks = get_task_subtasks(task_gid)
        stories = get_task_stories(task_gid)
        
        attachments_meta = []
        attachments = get_task_attachments(task_gid)
        if attachments and project_dir is not None:
            attachments_dir = os.path.join(project_dir, "attachments")
            attachments_dir = limit_path(attachments_dir, MAX_PATH_LENGTH)
            os.makedirs(attachments_dir, exist_ok=True)
            for att in attachments:
                att_details = get_attachment_details(att['gid'])
                file_path = download_attachment(att_details, attachments_dir, task_gid)
                att_details['downloaded_file'] = os.path.relpath(file_path, project_dir) if file_path else None
                attachments_meta.append(att_details)
        else:
            for att in attachments:
                att_details = get_attachment_details(att['gid'])
                attachments_meta.append(att_details)
        
        project_tasks.append({
            "task_details": task_info,
            "subtasks": subtasks,
            "stories": stories,
            "attachments": attachments_meta
        })
    
    project_data['tasks'] = project_tasks
    return project_data

@app.route("/", methods=["GET"])
def index():
    projects = get_projects()
    teams_api = get_teams()
    # Build a lookup mapping team gid to team name from teams_api
    team_map = {team["gid"]: team["name"] for team in teams_api}

    # Group projects by team.
    grouped = {}
    for project in projects:
        team_obj = project.get("team")
        if team_obj:
            team_gid = team_obj.get("gid")
            if team_gid not in team_map:
                team_info = get_team_details(team_gid)
                team_map[team_gid] = team_info.get("name", f"Team {team_gid}")
            team_name = team_map.get(team_gid, "Unknown Team")
        else:
            team_name = "No Team"
        grouped.setdefault(team_name, []).append(project)
    
    print("Teams API returned:", teams_api)
    print("Team map:", team_map)
    print("Grouped teams:", grouped)
    
    return render_template("index.html", teams=grouped)

@app.route("/export", methods=["POST"])
def export_projects():
    selected_ids = request.form.getlist("project_ids")
    export_all = request.form.get("export_all")
    projects = get_projects()
    
    if export_all == "all":
        selected_projects = projects
    else:
        selected_projects = [proj for proj in projects if proj['gid'] in selected_ids]
    
    if not selected_projects:
        flash("No projects selected for export.")
        return redirect(url_for("index"))
    
    # Create an in-memory ZIP file
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for proj in selected_projects:
            proj_data = export_project(proj, project_dir=None)
            json_str = json.dumps(proj_data, indent=4)
            safe_project_name = safe_filename(proj.get('name', 'project'))
            file_name = f"{safe_project_name}_{proj['gid']}.json"
            zf.writestr(file_name, json_str)
    memory_file.seek(0)
    return send_file(memory_file, attachment_filename="exported_projects.zip", as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
