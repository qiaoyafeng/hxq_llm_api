"""
记忆迁移脚本
从数据库读取 chat_log 表中的用户消息，调用 add_memory 接口迁移到目标记忆服务
"""
import argparse
import asyncio
from collections import defaultdict
from typing import Dict, List, Tuple

from configs.base import settings
from db.mysql import query_sql
from api.memory import add_memory
from logger import get_logger


logger = get_logger(__name__)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="记忆迁移脚本：从数据库读取消息并迁移到目标记忆服务"
    )
    parser.add_argument(
        "--target-url",
        type=str,
        required=True,
        help="目标记忆 API 地址，例如 http://192.168.1.100:8080",
    )
    parser.add_argument(
        "--target-key",
        type=str,
        required=True,
        help="目标记忆 API Key",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="开始日期，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="结束日期，格式 YYYY-MM-DD",
    )
    return parser.parse_args()


def override_settings(target_url: str, target_key: str):
    """覆盖 settings 中的记忆 API 配置，指向目标服务"""
    settings.HXQ_MEM_API_URL = target_url.rstrip("/")
    settings.HXQ_MEM_API_KEY = target_key
    settings.HXQ_MEM_ENABLED = True
    logger.info(f"已覆盖记忆 API 配置: URL={settings.HXQ_MEM_API_URL}")


def fetch_messages(start_date: str, end_date: str) -> List[Dict]:
    """从数据库读取指定时间范围内的消息"""
    sql = (
        f"SELECT user_id, role_id, role, content, create_time "
        f"FROM {settings.TABLE_CHAT_LOG} "
        f"WHERE create_time >= '{start_date}' AND create_time < '{end_date}' "
        f"AND user_id != 'archive_0001' "
        f"ORDER BY user_id, role_id, id"
    )
    logger.info(f"查询 SQL: {sql}")
    records = query_sql(sql)
    logger.info(f"查询到 {len(records)} 条消息记录")
    return records


def pair_messages(records: List[Dict]) -> List[Tuple[str, str, Dict[str, str]]]:
    """
    按 (user_id, role_id) 分组，只提取 role 为 user 的消息
    
    Returns:
        列表，每项为 (app_user_id, role_id, message_dict)
        message_dict 格式: {"user": "..."}
    """
    # 按 (user_id, role_id) 分组
    groups: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for record in records:
        key = (record["user_id"], record["role_id"])
        groups[key].append(record)
    
    paired = []
    for (user_id, role_id), msgs in groups.items():
        for msg in msgs:
            if msg["role"] == "user":
                message_dict = {"user": msg["content"] or ""}
                paired.append((user_id, role_id, message_dict))
    
    logger.info(f"共提取 {len(paired)} 条 user 消息")
    return paired


async def migrate(paired_messages: List[Tuple[str, str, Dict[str, str]]], max_retries: int = 3, delay: float = 0.5):
    """
    逐条调用 add_memory 进行迁移
    
    Args:
        paired_messages: 配对后的消息列表
        max_retries: 单条最大重试次数
        delay: 每次请求间隔（秒）
    """
    total = len(paired_messages)
    success_count = 0
    fail_count = 0
    
    for idx, (app_user_id, role_id, message) in enumerate(paired_messages, 1):
        content_preview = (message.get("user") or "")[:100]
        logger.info(f"[{idx}/{total}] 准备保存记忆: user_id={app_user_id}, role_id={role_id}, 内容={content_preview}")
        
        success = False
        for attempt in range(1, max_retries + 1):
            try:
                result = await add_memory(app_user_id, role_id, message)
                if result:
                    success = True
                    logger.info(f"[{idx}/{total}] 保存记忆成功: user_id={app_user_id}, role_id={role_id}, 内容={content_preview}")
                    break
                else:
                    logger.warning(f"[{idx}/{total}] 第 {attempt} 次尝试失败，user_id={app_user_id}, role_id={role_id}")
            except Exception as e:
                logger.error(f"[{idx}/{total}] 第 {attempt} 次尝试异常: {e}")
            
            if attempt < max_retries:
                await asyncio.sleep(delay)
        
        if success:
            success_count += 1
        else:
            fail_count += 1
            logger.error(f"[{idx}/{total}] 迁移失败（已重试 {max_retries} 次），user_id={app_user_id}, role_id={role_id}")
        
        if idx % 10 == 0 or idx == total:
            logger.info(f"迁移进度: {idx}/{total}，成功={success_count}，失败={fail_count}")
        
        await asyncio.sleep(delay)
    
    logger.info(f"迁移完成: 总数={total}，成功={success_count}，失败={fail_count}")
    return success_count, fail_count


def main():
    args = parse_args()
    
    # 覆盖配置
    override_settings(args.target_url, args.target_key)
    
    # 读取数据库
    records = fetch_messages(args.start_date, args.end_date)
    if not records:
        logger.info("未查询到任何消息记录，退出")
        return
    
    # 配对消息
    paired_messages = pair_messages(records)
    if not paired_messages:
        logger.info("未配对到任何消息，退出")
        return
    
    # 执行迁移
    success_count, fail_count = asyncio.run(migrate(paired_messages))
    
    print(f"\n========== 迁移结果 ==========")
    print(f"总数: {len(paired_messages)}")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"================================")


if __name__ == "__main__":
    main()
