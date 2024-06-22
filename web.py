import json

from datetime import datetime
import pymysql
from fastapi import FastAPI, HTTPException, Response
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import log
from db import DB
from job import JobScheduler, Job, JobExecutor

class Server:
    def __init__(self):
        self.scheduler : JobScheduler

    def get_running_jobs(self, job_id):
        # find job executor by job id
        return self.scheduler.executing_jobs.get(job_id)

    def init(self):
        DB.db().create_tables()
        def on_done(jes: list[JobExecutor]):
            for je in jes:
                stdout, _ = je.get_output()
                stderr, _ = je.get_error()
                retcode = je.return_code()

                stdout = '\n'.join(stdout)[:40960]
                stderr = '\n'.join(stderr)[:40960]

                DB.db().update_last_run(je.job.id, datetime.now(), retcode, stdout, stderr)
                log.get_logger().info("Job %s done, stdout: %s, stderr: %s, retcode: %d, updating db...",
                                      je.job.id, stdout, stderr, retcode)
        scheduler = JobScheduler(on_jobs_done=on_done)
        scheduler.start()
        self.scheduler = scheduler

    def load_jobs(self):
        all_jobs = DB.db().get_all_jobs()
        for j in all_jobs:
            if not j.enabled or (j.schedule == "@once" and j.last_run_utc is not None):
                continue
            self.scheduler.dispatch_job(j)

    def new_job(self, j: Job):
        try:
            jj = DB.db().insert_job(j)
            if jj and jj.enabled:
                self.scheduler.dispatch_job(jj)
            return jj
        except pymysql.err.IntegrityError as e:
            if e.args[0] == 1062:
                raise HTTPException(status_code=409, detail="Job already exists") from e
            else:
                log.get_logger().error("db error: %s", e)
                raise HTTPException(status_code=500, detail="Internal server error") from e

    @classmethod
    def instance(cls):
        instance = getattr(cls, "_instance", None)
        if instance is None:
            instance = cls()
            cls._instance = instance
        return instance

app = FastAPI()
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={"request": request}
    )

@app.post("/job", response_model=Job)
async def create_job(job: Job):
    try:
        Server.instance().new_job(job)
        return job
    except KeyError as e:
        log.get_logger().error("bad request: %s", e)
        raise HTTPException(status_code=400, detail="Bad request") from e

@app.post("/job/{job_id}/disable")
async def disable_job(job_id: int):
    DB.db().update_job(job_id, {"enabled": 0})
    # remove from scheudler
    Server.instance().scheduler.disable_job(job_id)
    return {"status": "ok"}

@app.post("/job/{job_id}/enable")
async def enable_job(job_id: int):
    DB.db().update_job(job_id, {"enabled": 1})
    j = DB.db().get_job(job_id)
    Server.instance().scheduler.dispatch_job(j)
    return {"status": "ok"}

@app.post("/job/{job_id}/run")
async def run_job(job_id: int):
    j = DB.db().get_job(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Job not found")
    je = Server.instance().scheduler.run_job_once(j)
    return {"status": "ok", "job_executor_id": je.id()}

@app.post("/job/{job_id}/del")
async def del_job(job_id: int):
    log.get_logger().info("deleting job %s", job_id)
    Server.instance().scheduler.disable_job(job_id)
    DB.db().del_job(job_id)
    return {"status": "ok"}

@app.get("/job/{job_id}", response_model=Job)
async def get_job(job_id: int):
    # get job from db
    j = DB.db().get_job(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return j

@app.get("/jobs", response_model=list[Job])
async def get_jobs():
    jobs = DB.db().get_all_jobs()
    # get running job and update status
    for j in jobs:
        je = Server.instance().get_running_jobs(j.id)
        if je and je.status() == "running":
            j.running_status = "running"
    return jobs


@app.post("/job/{job_id}/update")
async def update_job(job_id: int, job: Job):
    update_fields = {
        "schedule": job.schedule,
        "body": job.body,
        "meta": json.dumps(job.meta),
    }
    j = DB.db().update_job(job_id, update_fields)
    # remove from scheudler and add back
    Server.instance().scheduler.disable_job(job_id)
    Server.instance().scheduler.dispatch_job(j)
    return j

def get_job_output_from_db(job_id: int) -> dict:
    return DB.db().get_job_last_run_info(job_id)

@app.get("/job/{job_id}/stdout")
def get_job_stdout(job_id: int, response_class=HTMLResponse):
    out = get_job_output_from_db(job_id)["stdout"]
    return Response(content=out, media_type="text/plain")

@app.get("/job/{job_id}/stderr")
def get_job_stderr(job_id: int):
    out = get_job_output_from_db(job_id)["stderr"]
    return Response(content=out, media_type="text/plain")
