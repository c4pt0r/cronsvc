import os
import json
import time
import pymysql
import dotenv
import job
import utils
import log
dotenv.load_dotenv()

TIDB_HOST = os.getenv("TIDB_HOST") or 'localhost'
TIDB_PORT = os.getenv("TIDB_PORT") or 4000
TIDB_USER = os.getenv("TIDB_USER") or 'root'
TIDB_PASSWORD = os.getenv("TIDB_PASSWORD") or ''
TIDB_DATABASE = os.getenv("TIDB_DATABASE") or 'test'
TIDB_SSL_CERT = os.getenv("TIDB_SSL_VERIFY_CERT") or '/etc/ssl/cert.pem'

class DB(object):
    def __init__(self,
                 host = TIDB_HOST,
                 port = TIDB_PORT,
                 user = TIDB_USER,
                 password = TIDB_PASSWORD,
                 database = TIDB_DATABASE,
                 ssl_cert = TIDB_SSL_CERT):
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.database = database
        self.ssl_cert = ssl_cert
        self.conn = None

    def init(self):
        self.reconnect()

    def reconnect(self):
        self.conn = pymysql.connect(
            host = self.host,
            port = self.port,
            user = self.user,
            password = self.password,
            database = self.database,
            ssl_verify_cert = True,
            ssl_verify_identity = True,
            ssl_ca = self.ssl_cert,
        )

    def query(self, sql, args = None):
        max_tries = 10
        for i in range(max_tries):
            try:
                cursor = self.conn.cursor()
                cursor.execute(sql, args)
                return cursor
            except pymysql.err.ProgrammingError as e:
                raise e
            except Exception as e:
                if i == max_tries - 1:
                    raise e
                log.get_logger().error("db error: %s", e)
                log.get_logger().error("reconnecting to db... sleeping for %s seconds", 2 * i)
                time.sleep(2 * i)
                self.reconnect()
    
    def execute(self, sql, args = None):
        max_tries = 10
        for i in range(max_tries):
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute(sql, args)
                    self.conn.commit()
                    return cursor
            except pymysql.err.ProgrammingError as e:
                raise e
            except Exception as e:
                log.get_logger().error("db error: %s", e)
                if i == max_tries - 1:
                    raise e
                log.get_logger().error("reconnecting to db... sleeping for %s seconds", 2 * i)
                time.sleep(2 * i)
                self.reconnect()
    
    def execute_many(self, sql, values):
        max_tries = 10
        for i in range(max_tries):
            try:
                with self.conn.cursor() as cursor:
                    cursor.executemany(sql, values)
                    self.conn.commit()
                    return cursor
            except pymysql.err.ProgrammingError as e:
                raise e
            except Exception as e:
                log.get_logger().error("db error: %s", e)
                if i == max_tries - 1:
                    raise e
                log.get_logger().error("reconnecting to db... sleeping for %s seconds", 2 * i)
                time.sleep(2 * i)
                self.reconnect()
        
    def query_one(self, sql):
        cursor = self.query(sql)
        return cursor.fetchone()

    def execute_stmt(self, sql):
        self.execute(sql)

    def close(self):
        if self.conn:
            self.conn.close()

    def __del__(self):
        self.close()

    def ping(self):
        if not self.conn:
            return self.conn.ping()

    def create_tables(self):
        self.execute_stmt("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                schedule VARCHAR(255),
                body LONGTEXT,
                executor VARCHAR(255),
                meta TEXT,
                last_run_utc TIMESTAMP DEFAULT NULL,
                create_time_utc TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                enabled BOOLEAN DEFAULT TRUE,
                last_run_exit_code INT DEFAULT NULL,
                last_run_stdout LONGTEXT DEFAULT NULL,
                last_run_stderr LONGTEXT DEFAULT NULL,
                UNIQUE KEY (name)
            )
        """)

    def insert_job(self, j: job.Job) -> job.Job:
        self.execute("""
            INSERT INTO jobs (name, description, schedule, body, executor, meta, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (j.name, j.description, j.schedule, j.body, j.executor, json.dumps(j.meta), j.enabled))
        # get the last inserted id
        j.id = self.query_one("SELECT LAST_INSERT_ID()")[0]
        return j

    def get_job(self, job_id) -> job.Job:
        res = self.query_one(f"""
            SELECT 
                id , name, description, schedule,
                body, executor, meta, last_run_utc, create_time_utc, enabled
            FROM jobs WHERE id = {job_id}
        """)
        if not res:
            return None

        return job.Job(
            id = res[0],
            name = res[1],
            description = res[2],
            schedule = res[3],
            body = res[4],
            executor = res[5],
            meta = json.loads(res[6]),
            last_run_utc = res[7],
            create_time_utc = res[8],
            enabled = res[9],
        )

    def get_job_last_run_info(self, job_id):
        res = self.query_one(f"""
            SELECT last_run_exit_code, last_run_stdout, last_run_stderr, last_run_utc
            FROM jobs WHERE id = {job_id}
        """)
        if not res:
            return None

        return {
            "exit_code": res[0],
            "stdout": res[1],
            "stderr": res[2],
            "last_run_utc": res[3].strftime('%Y-%m-%d %H:%M:%S') if res[3] else None
        }

    def del_job(self, job_id):
        self.execute("""
            DELETE FROM jobs WHERE id = %s
        """, job_id)
        return job_id

    def get_all_jobs(self) -> list[job.Job]:
        res = self.query("""
            SELECT * FROM jobs ORDER BY id DESC
        """)
        jobs = []
        for r in res:
            j = job.Job(
                id = r[0],
                name = r[1],
                description = r[2],
                schedule = r[3],
                body = r[4],
                executor = r[5],
                meta = json.loads(r[6]),
                last_run_utc = r[7],
                create_time_utc = r[8],
                enabled = r[9],
                last_run_exit_code = r[10],
                last_run_stdout = r[11],
                last_run_stderr = r[12],
            )
            jobs.append(j)
        return jobs

    def update_job(self, jid, fields: dict):
        sets = []
        vals = []
        for k, v in fields.items():
            sets.append(f"`{k}` = %s")
            vals.append(v)

        if sets:
            fmt_str = "UPDATE jobs SET " + ", ".join(sets) + " WHERE id = %s"
            log.get_logger().info(fmt_str)
            self.execute(fmt_str, vals + [jid])
    
        return self.get_job(jid)

    def update_last_run(self, job_id, dt, exit_code = None, stdout = "", stderr= ""):
        utc_dt = utils.local_time_to_utc(dt)
        str_dt = utc_dt.strftime('%Y-%m-%d %H:%M:%S')
        log.get_logger().info("updating last run time of job %s to %s", job_id, str_dt)

        update_pairs = []
        value_pairs = []
        update_pairs.append("last_run_utc = %s")
        value_pairs.append(str_dt)
        if exit_code is not None:
            update_pairs.append("last_run_exit_code = %s")
            value_pairs.append(exit_code)
        if stdout:
            update_pairs.append("last_run_stdout = %s")
            value_pairs.append(stdout)
        if stderr:
            update_pairs.append("last_run_stderr = %s")
            value_pairs.append(stderr)

        self.execute("UPDATE jobs SET " + ", ".join(update_pairs) + " WHERE id = %s",
                     value_pairs + [job_id])
        return self.get_job(job_id)

    @classmethod
    def db(cls):
        # singleton
        instance = getattr(cls, "_instance", None)
        if instance is None:
            instance = cls()
            instance.init()
            cls._instance = instance
        return instance
