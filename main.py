import uvicorn
import argparse

from web import Server, app

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="host to listen on", default="localhost")
    parser.add_argument("--port", help="port to listen on", default=8001)
    args = parser.parse_args()

    Server.instance().init()
    Server.instance().load_jobs()
    uvicorn.run(app, host=args.host, port=int(args.port))