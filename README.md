# cronsvc

cronsvc, providing a simple RESTful API and Web UI to manage and execute scheduled tasks (like Cron jobs).

## Features

- Add, delete, and update Cron jobs via Web UI or API
- View the list of existing Cron jobs
- Enable/disable Cron jobs
- Manually trigger Cron job execution
- View the standard output and error output of Cron job executions
- Persist Cron jobs using SQLite database
- Render Web UI using Jinja2 template engine

## Installation and Running

1. Clone this repository:

   ```
   git clone https://github.com/c4pt0r/cronsvc
   cd cronsvc
   ```

2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Run the application:

   ```
   python main.py
   ```

   The application will run on `http://localhost:8000`.

## API Documentation

### Create a Cron Job

- **URL**: `/job`
- **Method**: `POST`
- **Request Body**:
  ```json
  {
    "schedule": "Cron expression",
    "body": "Command to execute",
    "meta": {
      "name": "Job name"
    }
  }
  ```
- **Response**:
  - Status Code: 200 OK
  - Response Body: Created Cron job object

### Get the List of Cron Jobs

- **URL**: `/jobs`
- **Method**: `GET`
- **Response**:
  - Status Code: 200 OK
  - Response Body: List of Cron job objects

### Get a Single Cron Job

- **URL**: `/job/{job_id}`
- **Method**: `GET`
- **Response**:
  - Status Code: 200 OK
  - Response Body: Cron job object

### Update a Cron Job

- **URL**: `/job/{job_id}/update`
- **Method**: `POST`
- **Request Body**:
  ```json
  {
    "schedule": "Cron expression",
    "body": "Command to execute",
    "meta": {
      "name": "Job name"
    }
  }
  ```
- **Response**:
  - Status Code: 200 OK
  - Response Body: Updated Cron job object

### Delete a Cron Job

- **URL**: `/job/{job_id}/del`
- **Method**: `POST`
- **Response**:
  - Status Code: 200 OK
  - Response Body:
    ```json
    {
      "status": "ok"
    }
    ```

### Enable a Cron Job

- **URL**: `/job/{job_id}/enable`
- **Method**: `POST`
- **Response**:
  - Status Code: 200 OK
  - Response Body:
    ```json
    {
      "status": "ok"
    }
    ```

### Disable a Cron Job

- **URL**: `/job/{job_id}/disable`
- **Method**: `POST`
- **Response**:
  - Status Code: 200 OK
  - Response Body:
    ```json
    {
      "status": "ok"
    }
    ```

### Manually Trigger a Cron Job

- **URL**: `/job/{job_id}/run`
- **Method**: `POST`
- **Response**:
  - Status Code: 200 OK
  - Response Body:
    ```json
    {
      "status": "ok",
      "job_executor_id": "Job executor ID"
    }
    ```

### Get Cron Job Standard Output

- **URL**: `/job/{job_id}/stdout`
- **Method**: `GET`
- **Response**:
  - Status Code: 200 OK
  - Response Body: Job standard output content

### Get Cron Job Error Output

- **URL**: `/job/{job_id}/stderr`
- **Method**: `GET`
- **Response**:
  - Status Code: 200 OK
  - Response Body: Job error output content

## Contributing

Feel free to submit issues and pull requests.

## License

This project is licensed under the [MIT License](LICENSE).
