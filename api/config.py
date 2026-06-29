from typing import List

from configs.base import settings
from db.mysql import query_sql, build_create, update_sql
from logger import get_logger
from .protocol import UpdateConfigRequest, GetConfigRequest

logger = get_logger(__name__)


async def get_config(
    request: GetConfigRequest
) -> List:
    sql = f"SELECT variable , value , set_time , set_by  FROM {settings.TABLE_SYS_CONFIG} WHERE variable = '{request.variable}'"
    logger.info(f"get_config SQL: {sql}")
    configs = query_sql(sql)
    return configs


async def update_config(request: UpdateConfigRequest):

    sql = f"SELECT variable , value , set_time , set_by  FROM {settings.TABLE_SYS_CONFIG} WHERE variable = '{request.variable}'"
    logger.info(f"get_config SQL: {sql}")
    configs = query_sql(sql)
    if configs:
        sql = f"UPDATE {settings.TABLE_SYS_CONFIG} SET value='{request.value}' WHERE  variable = '{request.variable}'"
        update_sql(sql)
        logger.info(f"update_config SQL : {sql} ")
    else:
        sql = f"INSERT INTO {settings.TABLE_SYS_CONFIG} (variable, value, set_by) VALUES ('{request.variable}', '{request.value}', '{request.set_by}')"
        update_sql(sql)
        logger.info(f"insert_config SQL : {sql} ")
