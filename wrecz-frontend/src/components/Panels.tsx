import Toggle from "./Toggle";
import type { WreczSettings } from "@/lib/wreczApi";

export type MenuItem = "App List" | "ENV" | "Conversation box";

export function MenuPanel({
  onSelect,
  unread,
}: {
  onSelect: (item: MenuItem) => void;
  unread: number;
}) {
  return (
    <div className="wrecz-menu-panel" role="menu" aria-label="Application menu">
      <button type="button" role="menuitem" onClick={() => onSelect("App List")}>
        App List
      </button>
      <div className="wrecz-menu-divider" />
      <button type="button" role="menuitem" onClick={() => onSelect("ENV")}>
        ENV
      </button>
      <div className="wrecz-menu-divider" />
      <button
        type="button"
        role="menuitem"
        className="wrecz-menu-conversation"
        onClick={() => onSelect("Conversation box")}
      >
        Conversation box
        {unread > 0 ? (
          <span className="wrecz-menu-badge" aria-label={`${unread} unread`}>
            {unread > 9 ? "9+" : unread}
          </span>
        ) : null}
      </button>
    </div>
  );
}

/**
 * Every toggle here writes through to the WRECZ security core.
 *
 * Internet Access is the SecurityCore session state; the other two are
 * runtime settings the Router and the internet gate read on each request.
 * With no backend connected the panel shows WRECZ's own safe defaults and
 * is disabled, rather than implying a setting that is not in effect.
 */
export function SettingsPanel({
  internetAccess,
  settings,
  disabled,
  onInternetChange,
  onSettingChange,
}: {
  internetAccess: boolean;
  settings: WreczSettings | null;
  disabled: boolean;
  onInternetChange: (value: boolean) => void;
  onSettingChange: (key: keyof WreczSettings, value: boolean) => void;
}) {
  const askBeforeWeb = settings?.ask_before_web ?? false;
  const confirmDestructive = settings?.confirm_destructive ?? true;
  const locked = disabled || settings === null;

  return (
    <div
      className={`wrecz-settings-panel ${locked ? "is-disabled" : ""}`}
      aria-label="Settings"
    >
      <div className="wrecz-settings-row">
        <span>Internet Access</span>
        <Toggle
          on={internetAccess}
          label="Internet Access"
          disabled={disabled}
          onChange={onInternetChange}
        />
      </div>

      <div className="wrecz-settings-row wrecz-settings-row--two-line">
        <span>Ask before web<br />access</span>
        <Toggle
          on={askBeforeWeb}
          label="Ask before web access"
          disabled={locked}
          onChange={(value) => onSettingChange("ask_before_web", value)}
        />
      </div>

      <div className="wrecz-settings-row wrecz-settings-row--two-line">
        <span>Confirm destructive<br />actions</span>
        <Toggle
          on={confirmDestructive}
          label="Confirm destructive actions"
          disabled={locked}
          onChange={(value) => onSettingChange("confirm_destructive", value)}
        />
      </div>

      <div className="wrecz-settings-footer">
        <span>Version - 1.0.0</span>
        <span>Model - Phi-4-mini</span>
      </div>
    </div>
  );
}

export function NotificationsPanel() {
  return (
    <div className="wrecz-notifications-panel" aria-label="Notifications">
      <span>Notifications</span>
    </div>
  );
}

export function AccountPanel() {
  return (
    <div className="wrecz-account-panel" aria-label="Account">
      <div className="wrecz-account-name">Ashutosh Mishra</div>
      <div className="wrecz-account-role">Administrator</div>
      <div className="wrecz-account-owner">OWNER</div>
    </div>
  );
}
