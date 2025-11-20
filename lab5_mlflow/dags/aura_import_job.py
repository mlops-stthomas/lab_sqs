"""Airflow DAG snippet to trigger and poll an Aura Import job.

This file is intentionally small and guards Airflow imports so the module
can be imported in environments without Airflow installed (e.g., unit tests).
"""
try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    from airflow.exceptions import AirflowSkipException
except Exception:  # pragma: no cover - import guarded
    DAG = None
    PythonOperator = None

from datetime import datetime, timedelta
import logging
from typing import Any

from lab5_mlflow.aura_import import get_token, create_import_job, get_job_status

logger = logging.getLogger('lab5_mlflow.aura_import')


def trigger_import_task(**ctx: Any):
    cfg = ctx.get('params', {})
    token = get_token(cfg['client_id'], cfg['client_secret'], oauth_url=cfg.get('oauth_url'))
    resp = create_import_job(token, cfg['organization_id'], cfg['project_id'], cfg['import_model_id'], cfg['db_id'], api_base=cfg.get('api_base'))
    # job id may be under 'id' or 'jobId' depending on API shape
    job_id = resp.get('id') or resp.get('jobId') or resp.get('job_id')
    if not job_id:
        logger.error('No job id returned from create_import_job: %s', resp)
        raise RuntimeError('Failed to start import job')
    ctx['ti'].xcom_push('aura_import_job_id', job_id)
    logger.info('Started aura import job %s', job_id)


def poll_import_task(**ctx: Any):
    cfg = ctx.get('params', {})
    job_id = ctx['ti'].xcom_pull(task_ids='trigger_aura_import', key='aura_import_job_id')
    if not job_id:
        raise AirflowSkipException('No job id in XCom')
    token = get_token(cfg['client_id'], cfg['client_secret'], oauth_url=cfg.get('oauth_url'))
    status = get_job_status(token, cfg['organization_id'], cfg['project_id'], job_id, api_base=cfg.get('api_base'))
    state = status.get('info', {}).get('state') or status.get('state')
    logger.info('Aura import job %s state=%s', job_id, state)
    if state and state.lower() in ('failed', 'cancelled', 'error'):
        raise RuntimeError(f'Aura import job {job_id} failed: {state}')
    if state and state.lower() in ('completed', 'success'):
        return
    # Not finished — re-raise to allow Airflow retry or external sensor to poll.
    raise RuntimeError('Job not complete yet')


if DAG is not None:
    default_args = {
        'owner': 'gepa',
        'depends_on_past': False,
        'retries': 1,
        'retry_delay': timedelta(minutes=2),
    }

    with DAG(
        dag_id='aura_import_job_dag',
        default_args=default_args,
        start_date=datetime(2025, 1, 1),
        schedule_interval=None,
        catchup=False,
    ) as dag:
        trigger = PythonOperator(task_id='trigger_aura_import', python_callable=trigger_import_task, provide_context=True)
        poll = PythonOperator(task_id='poll_aura_import', python_callable=poll_import_task, provide_context=True, retries=6)
        trigger >> poll
