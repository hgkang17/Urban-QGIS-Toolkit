# -*- coding: utf-8 -*-
import argparse
import configparser
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path

PLUGIN_DIR = "Urban_QGIS_Toolkit"


def read_metadata(path):
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    return parser["general"]


def build(metadata, repo, download_url, file_name):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
    version = metadata.get("version")

    plugins = ET.Element("plugins")
    plugin = ET.SubElement(plugins, "pyqgis_plugin",
                           name=metadata.get("name"), version=version, plugin_id="1")

    fields = {
        "description": metadata.get("description", ""),
        "about": metadata.get("about", "").strip(),
        "version": version,
        "qgis_minimum_version": metadata.get("qgisMinimumVersion", "3.22"),
        "qgis_maximum_version": metadata.get("qgisMaximumVersion", "3.99"),
        "homepage": metadata.get("homepage", repo),
        "file_name": file_name,
        "icon": f"https://raw.githubusercontent.com/{repo}/main/{PLUGIN_DIR}/{metadata.get('icon', 'logo.png')}",
        "author_name": metadata.get("author", ""),
        "download_url": download_url,
        "uploaded_by": metadata.get("author", ""),
        "create_date": now,
        "update_date": now,
        "experimental": metadata.get("experimental", "False"),
        "deprecated": metadata.get("deprecated", "False"),
        "trusted": "False",
        "server": metadata.get("server", "False"),
        "external_dependencies": metadata.get("plugin_dependencies", ""),
        "downloads": "0",
        "average_vote": "0",
        "rating_votes": "0",
        "tracker": metadata.get("tracker", ""),
        "repository": metadata.get("repository", ""),
        "tags": metadata.get("tags", ""),
        "changelog": metadata.get("changelog", "").strip(),
    }
    for tag, value in fields.items():
        ET.SubElement(plugin, tag).text = value

    ET.indent(plugins, space="  ")
    return ET.tostring(plugins, encoding="unicode")


def main():
    ap = argparse.ArgumentParser(description="QGIS 플러그인 저장소 XML 생성")
    ap.add_argument("--metadata", default=f"{PLUGIN_DIR}/metadata.txt")
    ap.add_argument("--repo", default="hgkang17/Urban-QGIS-Toolkit")
    ap.add_argument("--output", default="plugins.xml")
    args = ap.parse_args()

    metadata = read_metadata(args.metadata)
    version = metadata.get("version")
    # QGIS 는 file_name 의 첫 점 앞부분을 플러그인 ID 로 사용하므로
    # 반드시 설치 폴더명과 같아야 한다. 버전을 붙이면 업데이트 감지가 깨진다.
    file_name = f"{PLUGIN_DIR}.zip"
    download_url = (f"https://github.com/{args.repo}/releases/download/"
                    f"v{version}/{file_name}")

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + build(
        metadata, args.repo, download_url, file_name) + "\n"
    Path(args.output).write_text(xml, encoding="utf-8")
    print(f"{args.output} 생성 완료 (버전 {version})")
    print(f"다운로드 URL: {download_url}")


if __name__ == "__main__":
    main()
