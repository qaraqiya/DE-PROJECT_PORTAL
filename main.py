import boto3
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

REGION = "us-east-1"
BUCKET = "freedom-de-projects-s3"
s3 = boto3.client("s3", region_name=REGION)

def get_all_projects_directly():
    
    response = s3.list_objects_v2(Bucket=BUCKET, Delimiter='/')
    projects_list = []
    for prefix in response.get('CommonPrefixes', []):
        folder_name = prefix['Prefix'].strip('/')
        projects_list.append({
            "name": folder_name,
            "path": prefix['Prefix'] 
        })
    return {"All Projects": projects_list}

def get_contents_at_path(path):
  
    prefix = path if path.endswith('/') else path + '/'
    
    response = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, Delimiter='/')
    
    folders = []
    for p in response.get('CommonPrefixes', []):
        folders.append({
            "name": p['Prefix'].replace(prefix, "").strip('/'),
            "path": p['Prefix']
        })
        
    files = []
    if 'Contents' in response:
        for obj in response['Contents']:
            key = obj['Key']
            if key == prefix: continue 
            
            url = s3.generate_presigned_url(
                "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=3600
            )
            files.append({
                "name": key.split('/')[-1],
                "url": url
            })
            
    return folders, files

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    projects = get_all_projects_directly()
    return templates.TemplateResponse("index.html", {"request": request, "projects": projects})

@app.get("/project/{path:path}", response_class=HTMLResponse)
async def project_page(request: Request, path: str):
    folders, files = get_contents_at_path(path)
    return templates.TemplateResponse("project.html", {
        "request": request, 
        "folders": folders, 
        "files": files, 
        "project": path
    })
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)