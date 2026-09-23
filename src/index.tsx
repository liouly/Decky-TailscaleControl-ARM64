import {call, definePlugin} from "@decky/api";
import {ButtonItem, ConfirmModal, DropdownItem, Navigation, PanelSection, PanelSectionRow, showModal, staticClasses, TextField, ToggleField} from "@decky/ui";
import {useCallback, useEffect, useState} from "react";
import {FaExternalLinkAlt, FaNetworkWired, FaSignOutAlt, FaSlidersH, FaSync} from "react-icons/fa";

type Address = {interface: string; ipv4: string[]; ipv6: string[]};
type Peer = {hostname: string; ipv4: string; online: boolean; active: boolean};
type Status = {
  service: {installed: boolean; active: boolean; enabled: string; message: string};
  connection: {state: "connected" | "connecting" | "disconnected" | "stopped" | "unknown"; backend_state: string; online: boolean; health: string[]; connmark_unavailable: boolean; message: string};
  tailscale: {ipv4: string[]; ipv6: string[]; version: string; auth_url: string; peers: Peer[]; exit_nodes: Peer[]; selected_exit_node: string};
  network: {interfaces: Address[]; message: string};
};
type ActionResponse = {ok: true; status: Status} | {ok: false; status: Status; message: string};
type Preferences = {allow_lan_access: boolean; login_server: string; custom_flags: string};

const PREFERENCES_KEY = "decky-tailscale-control-preferences";

const connectionLabels: Record<Status["connection"]["state"], string> = {
  connected: "已连接",
  connecting: "正在连接",
  disconnected: "已断开",
  stopped: "服务已停止",
  unknown: "状态未知",
};

function values(items: string[]): string {
  return items.length ? items.join(", ") : "未分配";
}

function startupLabel(value: string): string {
  if (value === "enabled" || value === "enabled-runtime") return "已启用";
  if (value === "disabled") return "未启用";
  return value || "未知";
}

function loadPreferences(): Preferences {
  try {
    const stored = JSON.parse(localStorage.getItem(PREFERENCES_KEY) || "{}");
    return {
      allow_lan_access: stored.allow_lan_access !== false,
      login_server: typeof stored.login_server === "string" ? stored.login_server : "",
      custom_flags: typeof stored.custom_flags === "string" ? stored.custom_flags : "",
    };
  } catch {
    return {allow_lan_access: true, login_server: "", custom_flags: ""};
  }
}

function savePreferences(next: Preferences) {
  localStorage.setItem(PREFERENCES_KEY, JSON.stringify(next));
}

function statusNotice(status: Status): string {
  const issue = status.connection.message || status.network.message || status.service.message;
  if (issue) return `状态提示：${issue}`;
  if (status.connection.connmark_unavailable) {
    return "内核提示：连接标记规则不可用；当前 Tailscale 连接和普通 SSH 不受影响。";
  }
  if (status.connection.health.length) return `系统提示：${status.connection.health[0]}`;
  return "未发现影响连接的问题";
}

function AdvancedSettingsModal({initial, closeModal, onApply}: {initial: Preferences; closeModal: () => void; onApply: (next: Preferences) => void}) {
  const [loginServer, setLoginServer] = useState(initial.login_server);
  const [customFlags, setCustomFlags] = useState(initial.custom_flags);
  return <ConfirmModal
    closeModal={closeModal}
    strTitle="高级连接设置"
    strOKButtonText="应用"
    strCancelButtonText="取消"
    onCancel={closeModal}
    onOK={() => {
      onApply({...initial, login_server: loginServer.trim(), custom_flags: customFlags.trim()});
      closeModal();
    }}
  >
    <TextField label="登录服务器" value={loginServer} mustBeURL={Boolean(loginServer)} onChange={event => setLoginServer(event.currentTarget.value)} />
    <TextField label="自定义 up 参数" value={customFlags} onChange={event => setCustomFlags(event.currentTarget.value)} />
  </ConfirmModal>;
}

function LoginPanel({authUrl, serviceActive, working, preparing, message, onRequestUrl, onRefresh, onOpenWebLogin}: {
  authUrl: string;
  serviceActive: boolean;
  working: boolean;
  preparing: boolean;
  message: string;
  onRequestUrl: () => void;
  onRefresh: () => void;
  onOpenWebLogin: () => void;
}) {
  useEffect(() => {
    const refreshWhenReturning = () => onRefresh();
    window.addEventListener("focus", refreshWhenReturning);
    return () => window.removeEventListener("focus", refreshWhenReturning);
  }, [onRefresh]);

  const openWebLogin = () => {
    if (/^https?:\/\//.test(authUrl)) {
      onOpenWebLogin();
      Navigation.NavigateToExternalWeb(authUrl);
    }
  };

  return <PanelSection title="登录 Tailscale">
    <PanelSectionRow>此设备已退出当前账号。完成授权后会自动返回控制页面。</PanelSectionRow>
    {authUrl ? <ButtonItem childrenContainerWidth="max" disabled={working} onClick={openWebLogin}><FaExternalLinkAlt /> 去网页登录</ButtonItem> : null}
    {preparing ? <PanelSectionRow>正在准备登录地址...</PanelSectionRow> :
      <ButtonItem childrenContainerWidth="max" disabled={working || !serviceActive} onClick={onRequestUrl}><FaSync /> 重新获取登录地址</ButtonItem>}
    <ButtonItem childrenContainerWidth="max" disabled={working} onClick={onRefresh}><FaSync /> 刷新状态</ButtonItem>
    <PanelSectionRow><small style={{minHeight: "1.4em"}}>操作结果：{message || "等待登录授权"}</small></PanelSectionRow>
  </PanelSection>;
}

function Content() {
  const [status, setStatus] = useState<Status>();
  const [message, setMessage] = useState("正在读取 Tailscale 状态...");
  const [working, setWorking] = useState(false);
  const [logoutPending, setLogoutPending] = useState(false);
  const [webLoginOpen, setWebLoginOpen] = useState(false);
  const [preferences, setPreferences] = useState<Preferences>(loadPreferences);

  const refresh = useCallback(async () => {
    try {
      const next = await call<[], Status>("get_status");
      setStatus(next);
      setMessage("");
    } catch (error) {
      setMessage(`读取状态失败：${String(error)}`);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (logoutPending && status?.connection.backend_state === "NeedsLogin") setLogoutPending(false);
  }, [logoutPending, status?.connection.backend_state]);

  const needsLogin = Boolean(status && (logoutPending || status.connection.backend_state === "NeedsLogin"));

  useEffect(() => {
    if (!needsLogin) return;
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [needsLogin, refresh]);

  useEffect(() => {
    if (webLoginOpen && status?.connection.state === "connected") {
      setWebLoginOpen(false);
      Navigation.NavigateBack();
    }
  }, [webLoginOpen, status?.connection.state]);

  const handleResult = (result: ActionResponse, successMessage: string) => {
    setStatus(result.status);
    setMessage(result.ok ? successMessage : result.message);
  };

  const serviceAction = async (action: "restart") => {
    setWorking(true);
    try {
      const result = await call<["start" | "stop" | "restart"], ActionResponse>("service_action", action);
      handleResult(result, "Tailscale 服务已重启");
    } catch (error) {
      setMessage(`服务操作失败：${String(error)}`);
    } finally {
      setWorking(false);
    }
  };

  const networkAction = async (action: "up" | "down" | "reauth" | "set_exit" | "apply_settings" | "logout", settings: Record<string, unknown>, successMessage: string): Promise<boolean> => {
    setWorking(true);
    try {
      const result = await call<[string, Record<string, unknown>], ActionResponse>("network_action", action, settings);
      handleResult(result, successMessage);
      return result.ok;
    } catch (error) {
      setMessage(`网络操作失败：${String(error)}`);
      return false;
    } finally {
      setWorking(false);
    }
  };

  const updatePreferences = (next: Preferences) => {
    setPreferences(next);
    savePreferences(next);
  };

  const openAdvancedSettings = () => {
    let modal: {Close: () => void} | undefined;
    modal = showModal(
      <AdvancedSettingsModal
        initial={preferences}
        closeModal={() => modal?.Close()}
        onApply={next => {
          updatePreferences(next);
          void networkAction("apply_settings", next, "高级连接设置已应用");
        }}
      />,
      window,
      {strTitle: "高级连接设置", popupHeight: 420},
    );
  };

  const openLogoutConfirmation = () => {
    let modal: {Close: () => void} | undefined;
    modal = showModal(
      <ConfirmModal
        closeModal={() => modal?.Close()}
        strTitle="退出 Tailscale 登录"
        strOKButtonText="确认退出"
        strCancelButtonText="取消"
        onCancel={() => modal?.Close()}
        onOK={() => {
          modal?.Close();
          setLogoutPending(true);
          void networkAction("logout", {}, "已退出当前账号，请完成登录授权").then(succeeded => {
            if (!succeeded) setLogoutPending(false);
          });
        }}
      >
        退出后，此设备将断开 Tailnet，重新连接时需要再次完成授权登录。
      </ConfirmModal>,
      window,
      {strTitle: "退出 Tailscale 登录"},
    );
  };

  if (!status) return <PanelSection title="Tailscale"><PanelSectionRow>{message}</PanelSectionRow></PanelSection>;

  const controlsDisabled = working || !status.service.installed;
  const connected = status.connection.state === "connected" || status.connection.state === "connecting";
  if (needsLogin) return <LoginPanel
    authUrl={status.tailscale.auth_url}
    serviceActive={status.service.active}
    working={working}
    preparing={logoutPending && !status.tailscale.auth_url}
    message={message}
    onRequestUrl={() => void networkAction("reauth", {}, "已生成新的登录地址，旧地址已失效")}
    onRefresh={() => void refresh()}
    onOpenWebLogin={() => setWebLoginOpen(true)}
  />;
  const exitOptions = [
    {data: "", label: "不使用出口节点"},
    ...status.tailscale.exit_nodes.map(node => ({data: node.ipv4, label: `${node.hostname} (${node.ipv4})`})),
  ];
  return <>
    <PanelSection title="Tailscale 控制">
      <ToggleField
        label="Tailscale 连接"
        checked={connected}
        disabled={controlsDisabled}
        onChange={next => void networkAction(next ? "up" : "down", {}, next ? "正在连接 Tailscale" : "Tailscale 已断开")}
      />
      <ButtonItem childrenContainerWidth="max" disabled={controlsDisabled} onClick={() => void serviceAction("restart")}>
        <FaSync /> 重启 Tailscale
      </ButtonItem>
      <DropdownItem
        label="出口节点"
        menuLabel="出口节点"
        rgOptions={exitOptions}
        selectedOption={status.tailscale.selected_exit_node}
        disabled={controlsDisabled || !connected}
        onChange={option => void networkAction("set_exit", {exit_node: String(option.data), allow_lan_access: preferences.allow_lan_access}, "出口节点设置已更新")}
      />
      <ToggleField
        label="出口节点时保留局域网访问"
        checked={preferences.allow_lan_access}
        disabled={controlsDisabled || !connected || !status.tailscale.selected_exit_node}
        onChange={next => {
          const updated = {...preferences, allow_lan_access: next};
          updatePreferences(updated);
          void networkAction("set_exit", {exit_node: status.tailscale.selected_exit_node, allow_lan_access: next}, "局域网访问设置已更新");
        }}
      />
      <ButtonItem childrenContainerWidth="max" disabled={working} onClick={openAdvancedSettings}>
        <FaSlidersH /> 高级连接设置
      </ButtonItem>
      <ButtonItem childrenContainerWidth="max" disabled={working} onClick={() => void refresh()}><FaSync /> 刷新状态</ButtonItem>
      <PanelSectionRow><small style={{minHeight: "1.4em"}}>操作结果：{message || "就绪"}</small></PanelSectionRow>
    </PanelSection>
    <PanelSection title="连接状态">
      <PanelSectionRow>连接：{connectionLabels[status.connection.state]}；服务：{status.service.active ? "运行中" : "已停止"}</PanelSectionRow>
      <PanelSectionRow>开机启动：{startupLabel(status.service.enabled)}；版本：{status.tailscale.version || "未知"}</PanelSectionRow>
      <PanelSectionRow>Tailscale IPv4：{values(status.tailscale.ipv4)}</PanelSectionRow>
      <PanelSectionRow>Tailscale IPv6：{values(status.tailscale.ipv6)}</PanelSectionRow>
      <PanelSectionRow><small style={{minHeight: "1.4em"}}>{statusNotice(status)}</small></PanelSectionRow>
      {status.tailscale.auth_url && <PanelSectionRow><TextField label="登录地址" value={status.tailscale.auth_url} disabled bShowCopyAction /></PanelSectionRow>}
    </PanelSection>
    <PanelSection title="Tailnet 设备">
      {status.tailscale.peers.length === 0 && <PanelSectionRow>未发现其他设备</PanelSectionRow>}
      {status.tailscale.peers.map(peer => <PanelSectionRow key={`${peer.hostname}-${peer.ipv4}`}>
        {peer.hostname} - {peer.ipv4 || "无 IPv4"}；{peer.online ? "在线" : "离线"}{peer.active ? "；活动中" : ""}
      </PanelSectionRow>)}
    </PanelSection>
    <PanelSection title="本机网络地址">
      {status.network.interfaces.length === 0 && <PanelSectionRow>未发现可用的非 Tailscale 全局地址</PanelSectionRow>}
      {status.network.interfaces.map(item => <PanelSectionRow key={item.interface}>
        {item.interface} - IPv4：{values(item.ipv4)}；IPv6：{values(item.ipv6)}
      </PanelSectionRow>)}
    </PanelSection>
    <PanelSection title="账号操作">
      <ButtonItem childrenContainerWidth="max" disabled={working || !status.service.active} onClick={openLogoutConfirmation}>
        <FaSignOutAlt /> 退出 Tailscale 登录
      </ButtonItem>
    </PanelSection>
  </>;
}

export default definePlugin(() => ({
  name: "Tailscale Control",
  titleView: <div className={staticClasses.Title}>Tailscale</div>,
  content: <Content />,
  icon: <FaNetworkWired />,
}));
