import { useEffect, useRef, useState } from "react";
import imgSettings from "@/imports/Desktop5/0562518c500003ec1fad61bdc966af6f71b532d4.png";
import imgNotification from "@/imports/Desktop5/4c0f6170d297af1cf87ccdde4b3498489ea09db8.png";
import imgAccount from "@/imports/Desktop5/da37649a586de2327b5a61bc3ef657838dcfc0f8.png";
import imgMenu from "@/imports/Desktop5/d68274fc3312c0fbce80dcfb6a9b5380c79b9116.png";
import imgLogo from "@/assets/wrecz.svg";
import { useWrecz } from "@/hooks/useWrecz";
import Triangle from "./Triangle";
import Dropdown from "./Dropdown";
import ConversationPanel from "./ConversationPanel";
import VoiceVisualizer from "./VoiceVisualizer";
import WindowControls from "./WindowControls";
import ConfirmPrompt from "./ConfirmPrompt";
import {
  AccountPanel,
  MenuPanel,
  NotificationsPanel,
  SettingsPanel,
  type MenuItem,
} from "./Panels";

type Menu = "account" | "settings" | "notification" | "menu" | "conversation" | null;

export default function WreczApp() {
  const [openMenu, setOpenMenu] = useState<Menu>(null);
  const [input, setInput] = useState("");
  const [sendHover, setSendHover] = useState(false);
  const [activeEnv, setActiveEnv] = useState<"App List" | "ENV">("App List");
  const [readCount, setReadCount] = useState(0);

  const {
    connection,
    transcript,
    status,
    settings,
    busy,
    speaking,
    voice,
    pendingConfirm,
    send,
    answerConfirm,
    setInternet,
    changeSetting,
  } = useWrecz();

  const headerRef = useRef<HTMLElement>(null);

  // The transcript is no longer on screen, so the menu icon carries a count
  // of what arrived while the conversation box was closed.
  const conversationOpen = openMenu === "conversation";
  const unread = conversationOpen ? 0 : Math.max(0, transcript.length - readCount);

  useEffect(() => {
    if (conversationOpen) setReadCount(transcript.length);
  }, [conversationOpen, transcript.length]);

  const toggleMenu = (menu: Exclude<Menu, null>) => {
    setOpenMenu((current) => (current === menu ? null : menu));
  };

  const selectMenuItem = (item: MenuItem) => {
    if (item === "Conversation box") {
      setOpenMenu("conversation");
      return;
    }

    setActiveEnv(item);
    setOpenMenu(null);
  };

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (!headerRef.current?.contains(event.target as Node)) {
        setOpenMenu(null);
      }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenMenu(null);
    };

    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const submit = () => {
    const text = input.trim();
    if (!text) return;

    send(text);
    setInput("");
  };

  const online = connection === "online";

  return (
    <div className="wrecz-app">
      <WindowControls />

      <header ref={headerRef} className="wrecz-header" data-tauri-drag-region>
        <img className="wrecz-logo" src={imgLogo} alt="WRECZ" data-tauri-drag-region />

        <nav className="wrecz-header-actions" aria-label="WRECZ controls">
          <div className="wrecz-action">
            <button
              type="button"
              className="wrecz-icon-button"
              aria-label="Account"
              aria-expanded={openMenu === "account"}
              onClick={() => toggleMenu("account")}
            >
              <img src={imgAccount} alt="" />
            </button>
            <Dropdown open={openMenu === "account"}>
              <AccountPanel />
            </Dropdown>
          </div>

          <div className="wrecz-action">
            <button
              type="button"
              className="wrecz-icon-button"
              aria-label="Settings"
              aria-expanded={openMenu === "settings"}
              onClick={() => toggleMenu("settings")}
            >
              <img className={openMenu === "settings" ? "settings-open" : ""} src={imgSettings} alt="" />
            </button>
            <Dropdown open={openMenu === "settings"} className="dropdown-settings">
              <SettingsPanel
                internetAccess={status?.internet_enabled ?? false}
                settings={settings}
                disabled={!online}
                onInternetChange={setInternet}
                onSettingChange={changeSetting}
              />
            </Dropdown>
          </div>

          <div className="wrecz-action">
            <button
              type="button"
              className="wrecz-icon-button"
              aria-label="Notifications"
              aria-expanded={openMenu === "notification"}
              onClick={() => toggleMenu("notification")}
            >
              <img src={imgNotification} alt="" />
            </button>
            <Dropdown open={openMenu === "notification"} className="dropdown-notifications">
              <NotificationsPanel />
            </Dropdown>
          </div>

          <div className="wrecz-action">
            <button
              type="button"
              className="wrecz-icon-button"
              aria-label="App List, ENV and Conversation box"
              aria-expanded={openMenu === "menu" || conversationOpen}
              onClick={() => toggleMenu("menu")}
            >
              <img src={imgMenu} alt="" />
              {unread > 0 ? <span className="wrecz-unread-dot" aria-hidden="true" /> : null}
            </button>

            <Dropdown open={openMenu === "menu"} className="dropdown-menu">
              <MenuPanel onSelect={selectMenuItem} unread={unread} />
            </Dropdown>

            <Dropdown open={conversationOpen} className="dropdown-conversation">
              <ConversationPanel entries={transcript} busy={busy} />
            </Dropdown>
          </div>
        </nav>
      </header>

      <VoiceVisualizer speaking={speaking} voice={voice} />

      <main className="wrecz-main" aria-label="WRECZ workspace">
        {pendingConfirm ? (
          <ConfirmPrompt request={pendingConfirm} onAnswer={answerConfirm} />
        ) : null}

        <div className="wrecz-composer">
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            placeholder={online ? "Type here" : "Waiting for WRECZ..."}
            aria-label={`Message WRECZ in ${activeEnv}`}
          />

          <button
            type="button"
            className={`wrecz-send ${sendHover ? "is-hovered" : ""}`}
            aria-label="Send"
            onClick={submit}
            onMouseEnter={() => setSendHover(true)}
            onMouseLeave={() => setSendHover(false)}
          >
            <Triangle />
          </button>
        </div>
      </main>
    </div>
  );
}
