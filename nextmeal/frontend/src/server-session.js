const callbackKeys = ['access_token', 'refresh_token', 'expires_in', 'expires_at', 'token_type',
  'token_hash', 'type', 'auth', 'error', 'error_code', 'error_description', 'code'];

function authError(code, status) {
  const messages = {
    otp_expired: '인증 링크가 만료되었거나 이미 사용됐어요. 메일을 다시 요청해 주세요.',
    bad_jwt: '인증 링크를 확인할 수 없어요. 메일을 다시 요청해 주세요.',
    email_not_confirmed: '이메일 인증이 필요해요. 인증 메일을 확인하거나 다시 받아 주세요.',
    over_email_send_rate_limit: '메일을 너무 자주 요청했어요. 잠시 후 다시 시도해 주세요.',
    over_request_rate_limit: '요청이 많아요. 잠시 후 다시 시도해 주세요.',
    weak_password: '서버의 비밀번호 조건을 충족하지 못했어요. 더 강한 비밀번호를 입력해 주세요.',
    same_password: '기존 비밀번호와 다른 새 비밀번호를 입력해 주세요.',
    invalid_credentials: '이메일과 비밀번호를 확인해 주세요.',
    signup_disabled: '현재 회원가입이 중지되어 있어요. 잠시 후 다시 확인해 주세요.',
  };
  return Object.assign(new Error(messages[code] || '인증 요청을 완료하지 못했어요. 입력값을 확인하고 다시 시도해 주세요.'), {code, status});
}

export function readAuthCallback(href) {
  const url = new URL(href);
  const hash = new URLSearchParams(url.hash.slice(1));
  const value = key => hash.get(key) || url.searchParams.get(key);
  const type = value('type') || url.searchParams.get('auth');
  if (value('error') || value('error_code'))
    return {type, error: value('error_code') || value('error')};
  if (!['signup', 'email', 'recovery'].includes(type)) return null;
  if (value('token_hash')) return {type, token_hash: value('token_hash')};
  if (value('access_token')) return {
    type, access_token: value('access_token'), refresh_token: value('refresh_token'),
    expires_in: Number(value('expires_in')) || 3600,
    expires_at: Number(value('expires_at')) || null,
  };
  return {type, error: 'otp_expired'};
}

export function clearAuthCallback(href, history) {
  const url = new URL(href);
  const hash = new URLSearchParams(url.hash.slice(1));
  for (const key of callbackKeys) {
    url.searchParams.delete(key);
    hash.delete(key);
  }
  url.hash = hash.toString();
  history.replaceState(history.state, '', url);
}

function expiry(data) {
  const at = Number(data.expires_at), seconds = Number(data.expires_in);
  return Number.isFinite(at) && at > 0 ? at * 1000
    : Date.now() + (Number.isFinite(seconds) && seconds > 0 ? seconds : 3600) * 1000;
}

// Existing login sessions and short-lived password recovery use separate tab storage.
export function createSession(url, key, storage = null) {
  let session = null, recovery = null, refreshing = null, generation = 0;
  const storageKey = 'nextmeal-session:' + url;
  const recoveryKey = 'nextmeal-recovery:' + url;
  let persistEnabled = true;
  try {
    const saved = JSON.parse(storage?.getItem(storageKey) || 'null');
    if (saved?.access_token && saved?.refresh_token && Number.isFinite(saved.expires_at)) session = saved;
    const pending = JSON.parse(storage?.getItem(recoveryKey) || 'null');
    if (pending?.access_token && Number.isFinite(pending.expires_at)) recovery = pending;
  } catch {}
  function persist() {
    try {
      if (session && persistEnabled) storage?.setItem(storageKey, JSON.stringify(session));
      else storage?.removeItem(storageKey);
    } catch {}
  }
  function persistRecovery() {
    try {
      if (recovery) storage?.setItem(recoveryKey, JSON.stringify(recovery));
      else storage?.removeItem(recoveryKey);
    } catch {}
  }
  function clearRecovery() { recovery = null; persistRecovery(); }
  const base = url.replace(/\/$/, '');
  async function authRequest(path, body, token, method = 'POST') {
    const response = await fetch(base + '/auth/v1/' + path, {
      method,
      headers: {apikey: key, ...(body !== undefined ? {'Content-Type': 'application/json'} : {}),
        ...(token ? {Authorization: 'Bearer ' + token} : {})},
      ...(body !== undefined ? {body: JSON.stringify(body)} : {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw authError(data.error_code || data.code || data.error, response.status);
    return data;
  }
  function tokenSession(data) {
    if (!data.access_token || !data.refresh_token) throw new Error('로그인 응답이 올바르지 않습니다.');
    return {...data, expires_at: expiry(data)};
  }
  async function tokenRequest(body, grant) {
    return tokenSession(await authRequest('token?grant_type=' + grant, body));
  }
  function recoveryAccess() {
    if (!recovery || Date.now() >= recovery.expires_at) {
      clearRecovery();
      throw Object.assign(authError('otp_expired'), {recoveryExpired: true});
    }
    return recovery.access_token;
  }
  async function useRecovery(action) {
    try { return await action(recoveryAccess()); }
    catch (error) {
      if (error.status === 401 || ['otp_expired', 'bad_jwt'].includes(error.code)) {
        clearRecovery();
        error.recoveryExpired = true;
      }
      throw error;
    }
  }
  return {
    async signUp(email, password, redirect) {
      const current = ++generation;
      const data = await authRequest('signup?redirect_to=' + encodeURIComponent(redirect), {email: email.trim(), password});
      if (current !== generation) throw new Error('회원가입이 취소되었습니다.');
      if (data.access_token && data.refresh_token) {
        session = tokenSession(data);
        clearRecovery(); persist();
      }
      return data;
    },
    resendSignup(email, redirect) {
      return authRequest('resend?redirect_to=' + encodeURIComponent(redirect), {type: 'signup', email: email.trim()});
    },
    recover(email, redirect) {
      return authRequest('recover?redirect_to=' + encodeURIComponent(redirect), {email: email.trim()});
    },
    verifyRecovery(token) { return authRequest('verify', {token_hash: token, type: 'recovery'}); },
    resetPassword(token, password) { return authRequest('user', {password}, token, 'PUT'); },
    hasRecovery() { return Boolean(recovery); },
    clearRecovery,
    async acceptCallback(callback) {
      if (callback.error) throw authError(callback.error);
      const current = ++generation;
      let next;
      if (callback.token_hash) {
        next = await authRequest('verify', {token_hash: callback.token_hash, type: callback.type});
      } else {
        const user = await authRequest('user', undefined, callback.access_token, 'GET');
        next = {...callback, user};
      }
      if (current !== generation) throw new Error('인증이 취소되었습니다.');
      if (callback.type === 'recovery') {
        if (!next.access_token || expiry(next) <= Date.now()) throw authError('otp_expired');
        session = null; persist();
        recovery = {access_token: next.access_token, expires_at: expiry(next)};
        persistRecovery();
      } else {
        session = tokenSession(next);
        clearRecovery(); persist();
      }
      return next.user;
    },
    async restoreRecovery() {
      await useRecovery(token => authRequest('user', undefined, token, 'GET'));
    },
    async resetRecoveryPassword(password) {
      await useRecovery(token => authRequest('user', {password}, token, 'PUT'));
      clearRecovery();
    },
    async signIn(email, password) {
      const current = ++generation;
      const next = await tokenRequest({email: email.trim(), password}, 'password');
      if (current !== generation) throw new Error('로그인이 취소되었습니다.');
      session = next;
      clearRecovery(); persist();
      return next.user;
    },
    async accessToken() {
      if (!session) return null;
      if (Date.now() < session.expires_at - 60000) return session.access_token;
      if (!refreshing) {
        const current = generation;
        refreshing = tokenRequest({refresh_token: session.refresh_token}, 'refresh_token')
          .then(next => {if (current === generation) {session = next; persist();}})
          .catch(() => {if (current === generation) {session = null; persist();} throw new Error('로그인이 만료되었습니다. 다시 로그인하세요.');})
          .finally(() => {refreshing = null;});
      }
      await refreshing;
      return session?.access_token || null;
    },
    user() { return session?.user || null; },
    setPersistence(enabled) { persistEnabled = enabled; persist(); },
    clear() { generation++; session = null; persist(); clearRecovery(); },
  };
}
