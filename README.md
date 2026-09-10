# Urban QGIS Toolkit

도시계획·지적 실무에서 반복되는 작업을 자동화하는 QGIS 플러그인입니다.

- **개발자**: Huigu Kang
- **현재 버전**: 1.0.0
- **라이선스**: GPL-3.0-or-later
- **지원 버전**: QGIS 3.22 이상

---

## 설치 방법 (저장소 등록 방식 · 권장)

한 번만 저장소를 등록해 두면, 이후 새 버전이 나올 때 QGIS가 **자동으로 업데이트를 알려줍니다**.
ZIP 파일을 다시 내려받을 필요가 없습니다.

1. QGIS 실행
2. 상단 메뉴 **플러그인 → 플러그인 관리 및 설치** 클릭
3. 왼쪽 탭에서 **설정(Settings)** 선택
4. 하단 **저장소(Plugin Repositories)** 항목에서 **추가(Add)** 클릭
5. 아래 값을 입력하고 확인

   | 항목 | 입력값 |
   |---|---|
   | 이름 | `Urban QGIS Toolkit` |
   | URL | `https://raw.githubusercontent.com/hgkang17/Urban-QGIS-Toolkit/main/plugins.xml` |

6. **"시작할 때 업데이트 확인"** 옵션을 켜 두면 새 버전이 나올 때 알림을 받습니다.
7. 왼쪽 탭에서 **전체(All)** 를 선택하고 `Urban QGIS Toolkit` 을 검색하여 **플러그인 설치** 클릭

### ZIP 직접 설치 (대안)

[Releases](https://github.com/hgkang17/Urban-QGIS-Toolkit/releases) 페이지에서 최신 ZIP 파일을 내려받은 뒤,
**플러그인 관리 및 설치 → ZIP 파일로 설치** 에서 선택합니다.
이 방식은 자동 업데이트가 되지 않으므로 저장소 등록 방식을 권장합니다.

---

## 주요 기능

| 분류 | 기능 |
|---|---|
| 연속주제도 | MNUM 6자리 값 추출 및 범례 자동 분류 |
| 면적 | 레이어 면적(area) 자동 계산 |
| 심볼 | 선두께 일괄 조정, 심볼 복사·붙여넣기, 색상 일괄 지정 |
| 지적 | 연속지적도 PNU 주소 변환 |
| 검색 | 카카오맵 · 토지이음 연동 검색 (위치 확대 및 브라우저 실행) |
| 브이월드 | 공간정보 다운로드 페이지 연동, WFS · 2D 지도 API 호출 |
| 출력 | 지도 화면 JPG 내보내기 |
| 편의 | 라벨 필드 지정, 레이어 격리·정렬, 영역 확대 도구 |

## 사전 준비 (선택)

검색 연동 기능 일부는 [Playwright](https://playwright.dev/python/) 를 사용합니다.
플러그인 폴더의 `install_playwright.bat` 을 실행하면 설치할 수 있습니다.

플러그인 폴더 위치:
```
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\Urban_QGIS_Toolkit
```

---

## 라이선스

GNU General Public License v3.0 이상. 자세한 내용은 [LICENSE](LICENSE) 파일을 참고하세요.
