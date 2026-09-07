import { useState } from 'react';
import { setAuthToken } from '../api';
import { Button } from './ui/Button';
import { Card } from './ui/Card';

/** Shown when API calls fail auth — lets user paste ?token= without crafting the URL. */
export function AuthBanner({
  visible,
  onAuthed,
}: {
  visible: boolean;
  onAuthed: () => void;
}) {
  const [token, setToken] = useState('');
  const [saving, setSaving] = useState(false);
  if (!visible) return null;

  return (
    <Card className="auth-banner" role="alertdialog" aria-label="Access token needed">
      <div className="auth-banner-copy">
        <strong>Access token needed</strong>
        <span className="small muted">
          Paste the token from the SUPER start URL (<span className="mono">?token=…</span>), then continue.
        </span>
      </div>
      <form
        className="auth-banner-form"
        onSubmit={(e) => {
          e.preventDefault();
          const t = token.trim();
          if (!t) return;
          setSaving(true);
          setAuthToken(t);
          setSaving(false);
          onAuthed();
        }}
      >
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Paste token"
          aria-label="Access token"
          autoComplete="off"
          className="input"
        />
        <Button type="submit" variant="primary" size="sm" disabled={!token.trim() || saving}>
          Save & continue
        </Button>
      </form>
    </Card>
  );
}
