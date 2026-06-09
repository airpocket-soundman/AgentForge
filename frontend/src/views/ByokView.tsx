// BYOK (Bring Your Own Key) — intentionally a NON-FUNCTIONAL stub.
//
// The registration screen is shown (so the concept is visible), but inputs are
// disabled and an honest apology modal blocks use: server-side BYOK would let the
// operator misuse third-party keys, and we don't custody them in the hosted build.
// (See IMPLEMENTATION_GUIDE §2.6 "案2 補足".) BYOK is a self-host feature.
export function ByokView({ onBack }: { onBack: () => void }) {
  return (
    <div className="view byok">
      <div className="view__head">
        <button className="back" onClick={onBack}>← 戻る</button>
        <h2>🔑 API設定（BYOK）</h2>
      </div>

      {/* The form is rendered but disabled (visual only). */}
      <div className="byok-form" aria-hidden="true">
        <label>LLMプロバイダ
          <select disabled><option>Google Gemini</option></select>
        </label>
        <label>APIキー
          <input type="password" placeholder="sk-..." disabled />
        </label>
        <button disabled>保存する</button>
      </div>

      {/* Blocking apology modal. */}
      <div className="byok-modal__backdrop">
        <div className="byok-modal">
          <h3>🚧 この機能はまだ公開していません</h3>
          <p>
            BYOK（自分のAPIキーを使う機能）は試作（バイブ実装）の段階です。<br />
            サーバ側でAPIキーを預かる方式はセキュリティ上の責任が大きく、私自身まだ
            十分に勉強できていないため、<b>一般には公開していません</b>。ごめんなさい🙏
          </p>
          <p className="hint">
            将来は「自分でデプロイしたインスタンスに、自分の鍵を入れる」セルフホスト機能として
            提供予定です（運営者＝あなた自身なので安全）。
          </p>
          <button className="byok-back" onClick={onBack}>← 前の画面に戻る</button>
        </div>
      </div>
    </div>
  );
}
