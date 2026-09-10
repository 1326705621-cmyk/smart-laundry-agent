"""从命令行向开发数据库载入演示物品。"""

from smart_laundry.config import get_settings
from smart_laundry.demo_data import seed_demo_data


def main() -> None:
    settings = get_settings()
    inserted = seed_demo_data(settings.database_path)
    print(f"演示数据处理完成：新增 {inserted} 条。")
    print(f"数据库位置：{settings.database_path}")


if __name__ == "__main__":
    main()
