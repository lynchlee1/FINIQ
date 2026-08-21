from __future__ import annotations

import argparse
import json

from finiq.market_desk.web.features.disclosures.filter_presets import (
    migrate_filter_workflow_storage,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split disclosure filter results from filter.json metadata files."
    )
    parser.add_argument("data_root", help="Disclosure workspace root directory")
    args = parser.parse_args()
    result = migrate_filter_workflow_storage(args.data_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
