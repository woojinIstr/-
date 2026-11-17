# 회원가입 설정 점검과 A·D 전달 사항

## 실제 확인 결과

2026-11-17(한국 시간), 다음한끼 Supabase 프로젝트의 로그인된 대시보드에서 읽어 확인했습니다. 프로젝트 설정·계정·비밀번호는 변경하지 않았습니다.

| 항목 | 현재 값 | 의미 / 다음 작업 |
|---|---|---|
| Allow new users to sign up | ON | 신규 가입 허용 |
| Email provider | Enabled | 이메일·비밀번호 인증 사용 |
| Confirm email | ON | 이메일 인증이 필요함. A는 가입 완료와 로그인 완료를 구분해서 안내 |
| Site URL | http://localhost:3000 | 현재 통합본 주소(127.0.0.1:8000)와 다름. A·D가 콜백 처리·최종 URL을 확정한 뒤 맞춰야 함 |
| Redirect URLs | 없음 | 인증·비밀번호 복구의 실제 반환 주소 등록 필요 |
| Enable custom SMTP | OFF | 기본 메일 발송 상태. 일반 사용자 대상 출시 전 SMTP 제공자 설정과 수신 시험 필요 |

기존 로그인 성공은 가입·인증 메일 수신·비밀번호 복구 연결까지 검증했다는 뜻이 아닙니다. 이번에는 가입 요청이나 메일을 실제 발송하지 않았습니다.

## B가 추가한 재점검 도구

처음 `START_WINDOWS.cmd`로 실행한 뒤 루트의 `CHECK_SIGNUP_WINDOWS.cmd`를 더블클릭합니다. PowerShell에서 직접 실행하려면 통합본 폴더에서:

```powershell
.\backend\.venv\Scripts\python.exe .\backend\tools\check_auth_settings.py
```

backend/.env를 읽고 `/auth/v1/settings`에 GET 한 번만 보냅니다. 공개 Publishable 또는 anon key만 사용하며 키·토큰을 출력하지 않습니다. 신규 가입·이메일 로그인·인증 필요 여부를 표시합니다. 누락된 응답 필드는 ‘확인 필요’로 표시합니다. 주소·SMTP·메일 전달 성공 여부는 공개 설정 API로 확인할 수 없으므로 아래 절차로 확인합니다.

## A — 화면과 인증 복귀 처리

1. 회원가입, 인증 메일 안내·재발송, 비밀번호 복구 요청·새 비밀번호 입력 화면을 구현합니다.
2. Supabase 인증 반환을 처리할 정확한 URL과 흐름(PKCE 등)을 D와 확정합니다. 단순히 버튼과 signup 호출만 추가하면 끝나는 작업이 아닙니다.
3. Confirm email이 ON이므로 가입 응답에 세션이 없을 수 있습니다. ‘메일을 확인하세요’ 상태를 표시하고 인증 후 로그인이 되도록 처리합니다. 이미 가입된 이메일을 식별해 노출하려고 하지 않습니다.
4. 메일 링크 만료·잘못된 링크·동일 비밀번호 입력 오류·전송 제한을 표시하고 다시 요청할 경로를 제공합니다.
5. 현재 통합본은 루트 페이지를 정적으로 제공하며 별도 인증 경로의 SPA fallback은 없습니다. 새 `/auth/...` 경로를 쓸 경우 D와 서버 라우팅도 함께 구현하고 새로고침을 시험합니다.

## B·D — 확정 URL 반영과 메일 발송

1. Authentication → Sign In / Providers에서 신규 가입·Email 사용과 Confirm email 상태를 확인합니다. 현재 켜져 있습니다.
2. Authentication → URL Configuration에서 Site URL을 최종 사이트 주소로, Redirect URLs를 A가 실제 처리하는 정확한 반환 URL로 맞춥니다. 개발용 127.0.0.1과 localhost는 서로 다른 주소입니다. 운영용 주소를 임의의 예시 주소로 바꾸지 않습니다.
3. Authentication → Emails → SMTP Settings에 팀이 사용할 메일 발송 제공자를 설정합니다. 발신 도메인 인증과 제공자 자격 정보가 필요합니다. 비밀 값은 GitHub·프론트 코드에 넣지 않습니다.
4. 일반 사용자 주소로 가입 → 메일 수신 → 인증 링크 → 로그인 → 내 냉장고 접근을 시험합니다. 복구 메일 → 새 비밀번호 설정 → 재로그인도 별도로 시험합니다.
5. 두 계정의 작업물이 섞이지 않는지 확인합니다. 사용자별 workspace는 최초 인증 조회 때 기존과 같이 생성됩니다. 별도 신규 SQL은 필요 없습니다.

이 실행본에는 회원가입·비밀번호 복구 UI나 새 인증 콜백이 추가되지 않았습니다. 위 설정 점검과 후속 작업을 A·D에게 전달하세요.

## 공식 참고

- https://supabase.com/docs/guides/auth/general-configuration
- https://supabase.com/docs/guides/auth/redirect-urls
- https://supabase.com/docs/guides/auth/passwords
- https://supabase.com/docs/guides/auth/auth-smtp
- 공개 settings 필드: https://github.com/supabase/auth/blob/master/internal/api/settings.go
