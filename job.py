import os
import subprocess
import threading
import logging
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import utils
import log
from crontab import CronTab
from pydantic import BaseModel, Field

class Job(BaseModel):
    id : int | None = Field(None, title="ID of the job")
    name: str = Field("", title="Name of the job")
    executor: str = Field("shell", title="Executor of the job")
    description: str | None = Field("", title="Description of the job")
    schedule: str | None = Field("* * * * *", title="Cron schedule of the job")
    body: str = Field("", title="Body of the job")
    meta: dict | None = Field({},
                              title="Meta data of the job, if shell job, it will be passed as env vars")
    enabled : bool = Field(True, title="Enable status of the job")
    last_run_utc: datetime | None = Field(None, title="Last run time of the job")
    planned_next_run_utc: datetime | None = Field(None, title="Planned next run time of the job")
    last_run_exit_code: int | None = Field(None, title="Last run exit code of the job")
    last_run_stdout: str | None = Field(None, title="Last run stdout of the job")
    last_run_stderr: str | None = Field(None, title="Last run stderr of the job")
    running_status: str | None = Field(None, title="Running status of the job")

    def plan_next_run(self, dt = None):
        if self.schedule == "":
            now_utc = utils.local_time_to_utc(datetime.now())
            self.planned_next_run_utc = now_utc
            return
        if dt is None:
            try:
                dt = self.next_scheduled_run_utc()
            except Exception:
                return
        self.planned_next_run_utc = dt

    def next_scheduled_run_utc(self):
        cron_job = CronTab().new()
        cron_job.setall(self.schedule)
        schedule = cron_job.schedule(date_from=datetime.now())
        dt = schedule.get_next()
        utc_next_run = utils.local_time_to_utc(dt)
        return utc_next_run

class JobExecutor:
    def __init__(self, job: Job, logger=None, on_done=None, once=False):
        self.job = job
        self.output = []
        self.error = []
        self.once = once
        self.stat = "pending"
        self.retcode = 0
        self.running_process = None
        self.lock = threading.Lock()
        self.logger = logger or logging.getLogger("uvicorn")
        self.stash = {}
        self.on_done = on_done

    def exec_shell_cmd(self, cmd):
        # build env
        env = {}
        for k, v in self.job.meta.items():
            env[k] = v
        process = subprocess.Popen(cmd,
                                   shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True, env=env)
        self.running_process = process
        stdout, stderr = process.communicate()
        self.append_error(stderr)
        self.append_output(stdout)
        return process.returncode

    # run function will execute the job in worker thread
    def run(self):
        self.set_status("running")
        if self.job.executor == "shell":
            # ignore all the error from shell command
            try:
                retcode = self.exec_shell_cmd(self.job.body)
                self.set_return_code(retcode)
            except Exception as e:
                self.append_error(f"Error executing shell command: {e}")
        else:
            self.append_error(f"Executor {self.job.executor} not supported")
        self.set_status("done")
        if self.on_done:
            self.on_done(self)
        return 0, "\n".join(self.output), "\n".join(self.error)

    def get_job(self):
        return self.job

    def append_output(self, output):
        with self.lock:
            self.output.append(output)

    def append_error(self, error):
        with self.lock:
            self.error.append(error)

    def get_output(self, offset = 0):
        with self.lock:
            return self.output[offset:], len(self.output)

    def get_error(self):
        with self.lock:
            return self.error, len(self.error)

    def set_status(self, status):
        with self.lock:
            self.stat = status

    def setenv(self, key, value):
        with self.lock:
            self.stash[key] = value

    def env(self, key):
        with self.lock:
            return self.stash.get(key, None)

    def status(self):
        with self.lock:
            return self.stat

    def id(self):
        return self.job.id

    def get_result(self):
        with self.lock:
            return self.stash.get("result", {})

    def set_return_code(self, retcode):
        with self.lock:
            self.retcode = retcode
            
    def return_code(self):
        with self.lock:
            return self.retcode

    def stop(self):
        with self.lock:
            self.stat = "stop"
            if self.running_process:
                self.running_process.terminate()
                self.running_process = None

class JobWorkerPool:
    def __init__(self, max_workers = 0):
        if max_workers == 0:
            max_workers = os.cpu_count() / 2
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit_task(self, je: JobExecutor):
        self.executor.submit(je.run)
        return je

    def shutdown(self):
        self.executor.shutdown(wait=True)

# JobQueue is a priority queue for jobs, ordered by next scheduled run time
# if there's a same job scheduled, no need to add it again
class JobQueue:
    def __init__(self):
        self.jobs = []
        self.jobs_map = {}
        self.lock = threading.Lock()

    def add_job_if_not_exists(self, job: Job):
        with self.lock:
            if job.id in self.jobs_map:
                return
            self.jobs_map[job.id] = job
            self.jobs.append(job)
            self.jobs.sort(key=lambda x: x.planned_next_run_utc)

    def remove_job(self, job_id):
        with self.lock:
            if job_id in self.jobs_map:
                del self.jobs_map[job_id]
            self.jobs = list(filter(lambda x: x.id != job_id, self.jobs))

    def peak(self):
        with self.lock:
            if len(self.jobs) == 0:
                return None
            return self.jobs[0]

    def pop_job(self):
        with self.lock:
            if len(self.jobs) == 0:
                return None
            job = self.jobs.pop(0)
            del self.jobs_map[job.id]
            return job

class JobScheduler:
    def __init__(self, on_jobs_done=None):
        self.job_queue = JobQueue()
        self.worker_pool = JobWorkerPool()
        self.executing_jobs = utils.ThreadSafeMap()
        self.check_job_thread = threading.Thread(target=self.schedule_run, daemon=True)
        self.cleanup_done_job_thread = threading.Thread(target=self.cleanup_done_jobs, daemon=True)
        self.on_jobs_done = on_jobs_done

    def start(self):
        log.get_logger().info("starting job scheduler...")
        self.check_job_thread.start()
        self.cleanup_done_job_thread.start()

    def cleanup_done_jobs(self):
        while True:
            done_jobs = self.executing_jobs.remove_if(lambda _, v: v.status() == "done")
            # checking executing jobs, cleanning up done jobs
            # try not to hold lock for too long
            if len(done_jobs) > 0:
                log.get_logger().info("cleanup done jobs: %s", done_jobs)
                if self.on_jobs_done:
                    self.on_jobs_done(done_jobs)
                # if it's recurring job, plan next run
                for je in done_jobs:
                    job = je.get_job()
                    if len(job.schedule) > 0:
                        self.dispatch_job(job)
                    else:
                        log.get_logger().info("job %s is a one time job, remove from executing jobs", job.id)
            time.sleep(1)

    def schedule_run(self):
        while True:
            log.get_logger().debug("checking scheduled jobs...")
            job = self.job_queue.peak()
            if job is None:
                time.sleep(1)
                continue
            now = datetime.now()
            utc_now = utils.local_time_to_utc(now)
            log.get_logger().debug("next job scheduled at %s", job.planned_next_run_utc)
            log.get_logger().debug("current time is %s", utc_now)
            if job.planned_next_run_utc and job.planned_next_run_utc < utc_now:
                log.get_logger().info("dispatching job %s to execute", job)
                je = JobExecutor(job)
                self.worker_pool.submit_task(je)
                # remove from queue for this round
                self.job_queue.pop_job()
                self.executing_jobs[je.id()] = je
            time.sleep(1)

    def dispatch_job(self, job: Job, dt = None):
        job.plan_next_run(dt)
        self.job_queue.add_job_if_not_exists(job)

    def run_job_once(self, job: Job):
        log.get_logger().info("run job once: %s", job)
        je = JobExecutor(job, once = True)
        self.worker_pool.submit_task(je)
        self.executing_jobs[je.id()] = je
        return je

    def disable_job(self, job_id):
        log.get_logger().info("disable job %s, removed from scheduler", job_id)
        self.job_queue.remove_job(job_id)

    def get_executing_jobs(self):
        return self.executing_jobs.values()
