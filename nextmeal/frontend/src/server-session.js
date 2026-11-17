// Optional tab-scoped session persistence. Never put credentials in source or URLs.
export function createSession(url, key, storage = null) {
  let session = null, refreshing = null, generation = 0;
  const storageKey = 'nextmeal-session:' + url;
  let persistEnabled = true;
  try {const saved=JSON.parse(storage?.getItem(storageKey)||'null');if(saved?.access_token && saved?.refresh_token && Number.isFinite(saved.expires_at))session=saved;} catch {}
  function persist() {try {if(session && persistEnabled)storage?.setItem(storageKey,JSON.stringify(session));else storage?.removeItem(storageKey);}catch{}}
  const base = url.replace(/\/$/, '');
  async function tokenRequest(body, grant) {
    const response = await fetch(`${base}/auth/v1/token?grant_type=${grant}`, {
      method: 'POST', headers: { apikey: key, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.msg || data.error_description || '로그인 정보를 확인하세요.');
    if (!data.access_token || !data.refresh_token) throw new Error('로그인 응답이 올바르지 않습니다.');
    return { ...data, expires_at: Date.now() + (data.expires_in || 3600) * 1000 };
  }
  return {
    async signIn(email, password) {
      const current = ++generation;
      const next = await tokenRequest({ email: email.trim(), password }, 'password');
      if (current !== generation) throw new Error('로그인이 취소되었습니다.');
      session = next;
      persist();
      return next.user;
    },
    async accessToken() {
      if (!session) return null;
      if (Date.now() < session.expires_at - 60000) return session.access_token;
      if (!refreshing) {
        const current = generation;
        refreshing = tokenRequest({ refresh_token: session.refresh_token }, 'refresh_token')
          .then(next => { if (current === generation) {session = next;persist();} })
          .catch(() => { if (current === generation) {session = null;persist();} throw new Error('로그인이 만료되었습니다. 다시 로그인하세요.'); })
          .finally(() => { refreshing = null; });
      }
      await refreshing;
      return session?.access_token || null;
    },
    user() {return session?.user || null;},
    setPersistence(enabled) {persistEnabled=enabled;persist();},
    clear() { generation++; session = null;persist(); },
  };
}
