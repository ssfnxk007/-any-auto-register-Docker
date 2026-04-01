import { useEffect, useState } from 'react'
import { getConfig, getConfigOptions, getPlatforms, invalidateConfigCache, invalidateConfigOptionsCache, invalidatePlatformsCache } from '@/lib/app-data'
import type { ConfigOptionsResponse, ProviderDriver, ProviderOption, ProviderSetting } from '@/lib/config-options'
import { getCaptchaStrategyLabel } from '@/lib/config-options'
import { apiFetch } from '@/lib/utils'
import { ALL_OAUTH_PROVIDERS, getIdentityModeLabel, getOAuthProviderLabel } from '@/lib/registration'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Save, Eye, EyeOff, Mail, Shield, Cpu, RefreshCw, CheckCircle, XCircle, Sliders, Plus, X, Orbit, Package2, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

const ALL_IDENTITY_MODES = ['mailbox', 'oauth_browser']
type ProviderType = 'mailbox' | 'captcha'

function SettingsMetric({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: string | number
  icon: any
}) {
  return (
    <div className="rounded-[16px] border border-[var(--border)] bg-[var(--bg-pane)]/58 px-3 py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] tracking-[0.16em] text-[var(--text-muted)]">{label}</div>
          <div className="mt-0.5 text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)]">{value}</div>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-[12px] border border-[var(--border-soft)] bg-[var(--chip-bg)] text-[var(--accent)]">
          <Icon className="h-3.5 w-3.5" />
        </div>
      </div>
    </div>
  )
}

function PlatformCapsTab() {
  const [platforms, setPlatforms] = useState<any[]>([])
  const [drafts, setDrafts] = useState<Record<string, any>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [saved, setSaved] = useState<Record<string, boolean>>({})

  useEffect(() => {
    getPlatforms().then((list: any[]) => {
      setPlatforms(list)
      const init: Record<string, any> = {}
      list.forEach(p => {
        init[p.name] = {
          supported_identity_modes: [...p.supported_identity_modes],
          supported_oauth_providers: [...p.supported_oauth_providers],
        }
      })
      setDrafts(init)
    })
  }, [])

  const toggle = (name: string, field: string, value: string) => {
    setDrafts(d => {
      const arr: string[] = [...(d[name]?.[field] || [])]
      const idx = arr.indexOf(value)
      if (idx >= 0) arr.splice(idx, 1); else arr.push(value)
      return { ...d, [name]: { ...d[name], [field]: arr } }
    })
  }

  const save = async (name: string) => {
    setSaving(s => ({ ...s, [name]: true }))
    try {
      await apiFetch(`/platforms/${name}/capabilities`, { method: 'PUT', body: JSON.stringify(drafts[name]) })
      invalidatePlatformsCache()
      setSaved(s => ({ ...s, [name]: true }))
      setTimeout(() => setSaved(s => ({ ...s, [name]: false })), 2000)
    } finally { setSaving(s => ({ ...s, [name]: false })) }
  }

  const reset = async (name: string) => {
    await apiFetch(`/platforms/${name}/capabilities`, { method: 'DELETE' })
    invalidatePlatformsCache()
    const list = await getPlatforms({ force: true })
    const p = list.find((x: any) => x.name === name)
    if (p) setDrafts(d => ({ ...d, [name]: { supported_identity_modes: [...p.supported_identity_modes], supported_oauth_providers: [...p.supported_oauth_providers] } }))
  }

  return (
    <div className="space-y-4">
      {platforms.map(p => {
        const draft = drafts[p.name] || {}
        const modes: string[] = draft.supported_identity_modes || []
        const oauths: string[] = draft.supported_oauth_providers || []
        return (
          <div key={p.name} className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-pane)]/56 p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{p.display_name}</h3>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">{p.name} v{p.version}</p>
              </div>
              <button onClick={() => reset(p.name)}
                className="table-action-btn">
                恢复默认
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <p className="text-xs text-[var(--text-muted)] mb-2">注册身份</p>
                <div className="flex gap-4">
                  {ALL_IDENTITY_MODES.map(m => (
                    <label key={m} className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)] cursor-pointer">
                      <input type="checkbox" checked={modes.includes(m)}
                        onChange={() => toggle(p.name, 'supported_identity_modes', m)}
                        className="checkbox-accent" />
                      {getIdentityModeLabel(m)}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs text-[var(--text-muted)] mb-2">第三方入口</p>
                <div className="flex flex-wrap gap-4">
                  {ALL_OAUTH_PROVIDERS.map(o => (
                    <label key={o.value} className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)] cursor-pointer">
                      <input type="checkbox" checked={oauths.includes(o.value)}
                        onChange={() => toggle(p.name, 'supported_oauth_providers', o.value)}
                        className="checkbox-accent" />
                      {getOAuthProviderLabel(o.value)}
                    </label>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-4">
              <Button size="sm" onClick={() => save(p.name)} disabled={saving[p.name]}>
                <Save className="h-3.5 w-3.5 mr-1" />
                {saved[p.name] ? '已保存 ✓' : saving[p.name] ? '保存中...' : '保存'}
              </Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

const SELECT_FIELDS: Record<string, { label: string; value: string }[]> = {
  default_executor: [
    { label: '协议模式', value: 'protocol' },
    { label: '后台浏览器自动', value: 'headless' },
    { label: '可视浏览器自动', value: 'headed' },
  ],
  default_identity_provider: [
    { label: '系统邮箱', value: 'mailbox' },
    { label: '第三方账号', value: 'oauth_browser' },
  ],
  default_oauth_provider: [
    { label: '不预选，由当前页面选择', value: '' },
    { label: 'GitHub', value: 'github' },
    { label: 'Google', value: 'google' },
    { label: 'Microsoft', value: 'microsoft' },
    { label: 'LinkedIn', value: 'linkedin' },
    { label: 'Apple', value: 'apple' },
    { label: 'X', value: 'x' },
    { label: 'Builder ID', value: 'builderid' },
  ],
}

const TABS: { id: string; label: string; icon: any; sections?: any[] }[] = [
  {
    id: 'register', label: '注册策略', icon: Cpu,
    sections: [{
      section: '默认注册策略',
      desc: '这里配置的是默认行为，账号列表和注册页会直接复用这些设置。',
      items: [
        { key: 'default_identity_provider', label: '默认注册身份' },
        { key: 'default_oauth_provider', label: '默认第三方入口', placeholder: '' },
        { key: 'default_executor', label: '默认执行方式' },
      ],
    }, {
      section: '浏览器复用',
      desc: '第三方账号走后台浏览器自动时，通常需要复用本机已登录浏览器。',
      items: [
        { key: 'oauth_email_hint', label: '预期登录邮箱', placeholder: 'your-account@example.com' },
        { key: 'chrome_user_data_dir', label: 'Chrome Profile 路径', placeholder: '~/Library/Application Support/Google/Chrome' },
        { key: 'chrome_cdp_url', label: 'Chrome CDP 地址', placeholder: 'http://localhost:9222' },
      ],
    }],
  },
  {
    id: 'mailbox', label: '邮箱服务', icon: Mail,
    sections: [],
  },
  {
    id: 'captcha', label: '验证服务', icon: Shield,
    sections: [],
  },
  {
    id: 'platform_caps', label: '高级：平台能力', icon: Sliders,
    sections: [],
  },
  {
    id: 'chatgpt', label: 'ChatGPT', icon: Shield,
    sections: [{
      section: 'CPA 面板',
      desc: '注册完成后自动上传到 CPA 管理平台',
      items: [
        { key: 'cpa_api_url', label: 'API URL', placeholder: 'https://your-cpa.example.com' },
        { key: 'cpa_api_key', label: 'API Key', secret: true },
      ],
    }, {
      section: 'Sub2Api',
      desc: '注册完成后自动上传到 Sub2Api 管理平台，可使用 API Key 或管理员账号登录',
      items: [
        { key: 'sub2api_base_url', label: 'Base URL', placeholder: 'http://127.0.0.1:8080' },
        { key: 'sub2api_api_key', label: 'API Key', secret: true },
        { key: 'sub2api_admin_email', label: 'Admin Email', placeholder: 'admin@example.com' },
        { key: 'sub2api_admin_password', label: 'Admin Password', secret: true },
      ],
    }, {
      section: 'Team Manager',
      desc: '上传到自建 Team Manager 系统',
      items: [
        { key: 'team_manager_url', label: 'API URL', placeholder: 'https://your-tm.example.com' },
        { key: 'team_manager_key', label: 'API Key', secret: true },
      ],
    }],
  },
]

function Field({ field, form, setForm, showSecret, setShowSecret }: any) {
  const { key, label, placeholder, secret } = field
  const options = field.options || SELECT_FIELDS[key]
  return (
    <div className="grid grid-cols-3 gap-4 items-center py-3 border-b border-white/5 last:border-0">
      <label className="text-sm text-[var(--text-secondary)] font-medium">{label}</label>
      <div className="col-span-2 relative">
        {options ? (
          <select
            value={form[key] || options[0].value}
            onChange={e => setForm((f: any) => ({ ...f, [key]: e.target.value }))}
            className="control-surface appearance-none"
          >
            {options.map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        ) : (
          <>
            <input
              type={secret && !showSecret[key] ? 'password' : 'text'}
              value={form[key] || ''}
              onChange={e => setForm((f: any) => ({ ...f, [key]: e.target.value }))}
              placeholder={placeholder}
              className="control-surface pr-10"
            />
            {secret && (
              <button
                onClick={() => setShowSecret((s: any) => ({ ...s, [key]: !s[key] }))}
                className="absolute right-3 top-2.5 text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              >
                {showSecret[key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function ProviderField({ field, value, onChange, showSecret, setShowSecret, secretKey, disabled = false }: any) {
  const { label, placeholder, secret } = field
  return (
    <div className="grid grid-cols-3 gap-4 items-center py-3 border-b border-white/5 last:border-0">
      <label className="text-sm text-[var(--text-secondary)] font-medium">{label}</label>
      <div className="col-span-2 relative">
        <input
          type={secret && !showSecret[secretKey] ? 'password' : 'text'}
          value={value || ''}
          onChange={e => onChange(e.target.value)}
          disabled={disabled}
          placeholder={placeholder}
          className="control-surface pr-10 disabled:opacity-70"
        />
        {secret && (
          <button
            onClick={() => setShowSecret((s: any) => ({ ...s, [secretKey]: !s[secretKey] }))}
            disabled={disabled}
            className="absolute right-3 top-2.5 text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
          >
            {showSecret[secretKey] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>
    </div>
  )
}

function ProviderDetailModal({
  title,
  item,
  readOnly,
  saving,
  saved,
  showSecret,
  setShowSecret,
  onClose,
  onEdit,
  onChangeName,
  onChangeAuthMode,
  onChangeField,
  onSave,
}: any) {
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog-panel dialog-panel-md overflow-y-auto" style={{ maxHeight: '90vh' }} onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <div>
            <h2 className="text-base font-semibold text-[var(--text-primary)]">{title}</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">{item.display_name || item.catalog_label} · {item.provider_key}</p>
          </div>
          <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"><X className="h-4 w-4" /></button>
        </div>
        <div className="px-6 py-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-[var(--border)] bg-[var(--bg-hover)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]">
              {item.auth_modes.find((mode: any) => mode.value === item.auth_mode)?.label || item.auth_mode || '未设置认证方式'}
            </span>
            {item.is_default ? (
              <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-300">默认 Provider</span>
            ) : null}
          </div>
          {item.description ? (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-hover)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              {item.description}
            </div>
          ) : null}
          <div className="grid grid-cols-3 gap-4 items-center py-3 border-b border-white/5">
            <label className="text-sm text-[var(--text-secondary)] font-medium">配置名称</label>
            <div className="col-span-2">
              <input
                type="text"
                value={item.display_name || ''}
                onChange={e => onChangeName(e.target.value)}
                disabled={readOnly}
                placeholder={item.catalog_label}
                className="control-surface disabled:opacity-70"
              />
            </div>
          </div>
          {item.auth_modes?.length > 0 && (
            <div className="grid grid-cols-3 gap-4 items-center py-3 border-b border-white/5">
              <label className="text-sm text-[var(--text-secondary)] font-medium">认证方式</label>
              <div className="col-span-2">
                <select
                  value={item.auth_mode}
                  onChange={e => onChangeAuthMode(e.target.value)}
                  disabled={readOnly}
                  className="control-surface appearance-none disabled:opacity-70"
                >
                  {item.auth_modes.map((mode: any) => <option key={mode.value} value={mode.value}>{mode.label}</option>)}
                </select>
              </div>
            </div>
          )}
          {item.fields.length === 0 ? (
            <div className="text-sm text-[var(--text-muted)] py-3">这个 provider 当前无需额外配置。</div>
          ) : item.fields.map((field: any) => (
            <ProviderField
              key={field.key}
              field={field}
              value={field.category === 'auth' ? item.auth?.[field.key] : item.config?.[field.key]}
              onChange={(value: string) => onChangeField(field, value)}
              showSecret={showSecret}
              setShowSecret={setShowSecret}
              secretKey={`${item.provider_key}:${field.key}`}
              disabled={readOnly}
            />
          ))}
        </div>
        <div className="flex gap-3 px-6 py-4 border-t border-[var(--border)]">
          {readOnly ? (
            <>
              <Button onClick={onEdit} className="flex-1">切换到编辑</Button>
              <Button variant="outline" onClick={onClose} className="flex-1">关闭</Button>
            </>
          ) : (
            <>
              <Button onClick={onSave} disabled={saving} className="flex-1">
                <Save className="h-4 w-4 mr-2" />
                {saved ? '已保存 ✓' : saving ? '保存中...' : '保存'}
              </Button>
              <Button variant="outline" onClick={onClose} className="flex-1">取消</Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function AddProviderModal({
  title,
  providerType,
  providers,
  selectedKey,
  creating,
  onSelect,
  onClose,
  onCreate,
}: any) {
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog-panel dialog-panel-sm" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <div>
            <h2 className="text-base font-semibold text-[var(--text-primary)]">{title}</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">{providerType === 'mailbox' ? '从邮箱 provider catalog 中选择' : '从验证 provider catalog 中选择'}</p>
          </div>
          <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"><X className="h-4 w-4" /></button>
        </div>
        <div className="px-6 py-4">
          {providers.length === 0 ? (
            <div className="empty-state-panel">
              当前可新增的 provider 已全部加入列表。
            </div>
          ) : (
            <div className="space-y-3">
              <label className="block text-sm text-[var(--text-secondary)]">选择 Provider</label>
              <select
                value={selectedKey}
                onChange={e => onSelect(e.target.value)}
                className="control-surface appearance-none"
              >
                {providers.map((provider: ProviderOption) => (
                  <option key={provider.value} value={provider.value}>{provider.label}</option>
                ))}
              </select>
              {providers.find((provider: ProviderOption) => provider.value === selectedKey)?.description ? (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-hover)] px-3 py-2 text-xs text-[var(--text-secondary)]">
                  {providers.find((provider: ProviderOption) => provider.value === selectedKey)?.description}
                </div>
              ) : null}
            </div>
          )}
        </div>
        <div className="flex gap-3 px-6 py-4 border-t border-[var(--border)]">
          <Button
            onClick={() => onCreate(selectedKey)}
            disabled={providers.length === 0 || !selectedKey || creating}
            className="flex-1"
          >
            <Plus className="h-4 w-4 mr-2" />
            {creating ? '新增中...' : '新增'}
          </Button>
          <Button variant="outline" onClick={onClose} className="flex-1">取消</Button>
        </div>
      </div>
    </div>
  )
}

function CreateProviderDefinitionModal({
  title,
  providerType,
  drivers,
  form,
  creating,
  showSecret,
  setShowSecret,
  onChange,
  onClose,
  onCreate,
}: any) {
  const currentDriver = drivers.find((item: ProviderDriver) => item.driver_type === form.driver_type) || null
  const currentAuthModes = currentDriver?.auth_modes || []
  const currentFields = currentDriver?.fields || []

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog-panel dialog-panel-md overflow-y-auto" style={{ maxHeight: '90vh' }} onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <div>
            <h2 className="text-base font-semibold text-[var(--text-primary)]">{title}</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">新增一个动态 provider definition，并同时创建首个可用配置。</p>
          </div>
          <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"><X className="h-4 w-4" /></button>
        </div>
        <div className="px-6 py-4 space-y-3">
          <div className="grid grid-cols-3 gap-4 items-center py-3 border-b border-white/5">
            <label className="text-sm text-[var(--text-secondary)] font-medium">Provider 名称</label>
            <div className="col-span-2">
              <input value={form.label} onChange={e => onChange('label', e.target.value)} placeholder="My Mail Provider" className="control-surface" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4 items-center py-3 border-b border-white/5">
            <label className="text-sm text-[var(--text-secondary)] font-medium">Provider Key</label>
            <div className="col-span-2">
              <input value={form.provider_key} onChange={e => onChange('provider_key', e.target.value)} placeholder="my_mail_provider" className="control-surface" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4 items-center py-3 border-b border-white/5">
            <label className="text-sm text-[var(--text-secondary)] font-medium">描述</label>
            <div className="col-span-2">
              <input value={form.description} onChange={e => onChange('description', e.target.value)} placeholder="可选" className="control-surface" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4 items-center py-3 border-b border-white/5">
            <label className="text-sm text-[var(--text-secondary)] font-medium">驱动族</label>
            <div className="col-span-2">
              <select value={form.driver_type} onChange={e => onChange('driver_type', e.target.value)} className="control-surface appearance-none">
                {drivers.map((driver: ProviderDriver) => (
                  <option key={driver.driver_type} value={driver.driver_type}>{driver.label}</option>
                ))}
              </select>
              {currentDriver?.description ? <p className="mt-2 text-xs text-[var(--text-muted)]">{currentDriver.description}</p> : null}
            </div>
          </div>
          {currentAuthModes.length > 0 && (
            <div className="grid grid-cols-3 gap-4 items-center py-3 border-b border-white/5">
              <label className="text-sm text-[var(--text-secondary)] font-medium">认证方式</label>
              <div className="col-span-2">
                <select value={form.auth_mode} onChange={e => onChange('auth_mode', e.target.value)} className="control-surface appearance-none">
                  {currentAuthModes.map((mode: any) => (
                    <option key={mode.value} value={mode.value}>{mode.label}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
          {currentFields.length === 0 ? (
            <div className="text-sm text-[var(--text-muted)] py-3">这个驱动族当前无需额外配置字段。</div>
          ) : currentFields.map((field: any) => (
            <ProviderField
              key={field.key}
              field={field}
              value={field.category === 'auth' ? form.auth[field.key] : form.config[field.key]}
              onChange={(value: string) => {
                if (field.category === 'auth') {
                  onChange('auth', { ...form.auth, [field.key]: value })
                } else {
                  onChange('config', { ...form.config, [field.key]: value })
                }
              }}
              showSecret={showSecret}
              setShowSecret={setShowSecret}
              secretKey={`create:${providerType}:${field.key}`}
            />
          ))}
        </div>
        <div className="flex gap-3 px-6 py-4 border-t border-[var(--border)]">
          <Button onClick={onCreate} disabled={creating} className="flex-1">
            <Plus className="h-4 w-4 mr-2" />
            {creating ? '创建中...' : '创建并启用'}
          </Button>
          <Button variant="outline" onClick={onClose} className="flex-1">取消</Button>
        </div>
      </div>
    </div>
  )
}

export default function Settings() {
  const [activeTab, setActiveTab] = useState('register')
  const [form, setForm] = useState<Record<string, string>>({})
  const [configOptions, setConfigOptions] = useState<ConfigOptionsResponse>({ mailbox_providers: [], captcha_providers: [], mailbox_drivers: [], captcha_drivers: [], captcha_policy: {} })
  const [providerSettings, setProviderSettings] = useState<{ mailbox: ProviderSetting[]; captcha: ProviderSetting[] }>({ mailbox: [], captcha: [] })
  const [newProviderKey, setNewProviderKey] = useState<{ mailbox: string; captcha: string }>({ mailbox: '', captcha: '' })
  const [providerDialog, setProviderDialog] = useState<{ providerType: ProviderType | null; providerKey: string; readOnly: boolean }>({ providerType: null, providerKey: '', readOnly: false })
  const [providerAddDialog, setProviderAddDialog] = useState<ProviderType | null>(null)
  const [providerCreateDialog, setProviderCreateDialog] = useState<ProviderType | null>(null)
  const [providerDefinitionCreating, setProviderDefinitionCreating] = useState<Record<string, boolean>>({})
  const [providerDefinitionForm, setProviderDefinitionForm] = useState<Record<ProviderType, any>>({
    mailbox: { provider_key: '', label: '', description: '', driver_type: '', auth_mode: '', config: {}, auth: {} },
    captcha: { provider_key: '', label: '', description: '', driver_type: '', auth_mode: '', config: {}, auth: {} },
  })
  const [optionsError, setOptionsError] = useState('')
  const [providerNotice, setProviderNotice] = useState<{ mailbox: string; captcha: string }>({ mailbox: '', captcha: '' })
  const [providerError, setProviderError] = useState<{ mailbox: string; captcha: string }>({ mailbox: '', captcha: '' })
  const [showSecret, setShowSecret] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [providerSaving, setProviderSaving] = useState<Record<string, boolean>>({})
  const [providerSaved, setProviderSaved] = useState<Record<string, boolean>>({})
  const [providerDeleting, setProviderDeleting] = useState<Record<string, boolean>>({})
  const [providerCreating, setProviderCreating] = useState<Record<string, boolean>>({})
  const [solverRunning, setSolverRunning] = useState<boolean | null>(null)

  const loadConfigData = async () => {
    const [cfg, options] = await Promise.all([
      getConfig().catch(() => ({})),
      getConfigOptions().catch(() => null),
    ])
    setForm(cfg)
    if (options) {
      setConfigOptions(options)
      const nextMailbox = options.mailbox_settings || []
      const nextCaptcha = options.captcha_settings || []
      setProviderSettings({
        mailbox: nextMailbox,
        captcha: nextCaptcha,
      })
      setOptionsError('')
    } else {
      setConfigOptions({ mailbox_providers: [], captcha_providers: [], mailbox_drivers: [], captcha_drivers: [], captcha_policy: {} })
      setProviderSettings({ mailbox: [], captcha: [] })
      setOptionsError('未加载到 provider 元数据。请重启后端后刷新页面。')
    }
  }

  useEffect(() => {
    loadConfigData()
  }, [])

  const checkSolver = async () => {
    try { const d = await apiFetch('/solver/status'); setSolverRunning(d.running) }
    catch { setSolverRunning(false) }
  }
  const restartSolver = async () => {
    await apiFetch('/solver/restart', { method: 'POST' })
    setSolverRunning(null)
    setTimeout(checkSolver, 4000)
  }
  useEffect(() => { checkSolver() }, [])

  const save = async () => {
    setSaving(true)
    try {
      await apiFetch('/config', { method: 'PUT', body: JSON.stringify({ data: form }) })
      invalidateConfigCache()
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }

  const tab = TABS.find(t => t.id === activeTab) ?? TABS[0]
  const sections = tab.sections ?? []
  const mailboxCatalog = configOptions.mailbox_providers || []
  const captchaCatalog = configOptions.captcha_providers || []
  const mailboxDrivers = configOptions.mailbox_drivers || []
  const captchaDrivers = configOptions.captcha_drivers || []
  const unusedMailboxProviders = mailboxCatalog.filter(item => !providerSettings.mailbox.some(setting => setting.provider_key === item.value))
  const unusedCaptchaProviders = captchaCatalog.filter(item => !providerSettings.captcha.some(setting => setting.provider_key === item.value))

  useEffect(() => {
    setNewProviderKey(current => {
      const nextMailbox = unusedMailboxProviders.some(item => item.value === current.mailbox) ? current.mailbox : (unusedMailboxProviders[0]?.value || '')
      const nextCaptcha = unusedCaptchaProviders.some(item => item.value === current.captcha) ? current.captcha : (unusedCaptchaProviders[0]?.value || '')
      if (current.mailbox === nextMailbox && current.captcha === nextCaptcha) {
        return current
      }
      return {
        mailbox: nextMailbox,
        captcha: nextCaptcha,
      }
    })
  }, [mailboxCatalog, captchaCatalog, providerSettings.mailbox, providerSettings.captcha])

  useEffect(() => {
    setProviderDefinitionForm(current => {
      const next = { ...current }
      const mailboxDriver = mailboxDrivers.find(item => item.driver_type === current.mailbox.driver_type) || mailboxDrivers[0] || null
      const captchaDriver = captchaDrivers.find(item => item.driver_type === current.captcha.driver_type) || captchaDrivers[0] || null
      next.mailbox = {
        ...next.mailbox,
        driver_type: mailboxDriver?.driver_type || '',
        auth_mode: mailboxDriver?.auth_modes?.some(mode => mode.value === next.mailbox.auth_mode)
          ? next.mailbox.auth_mode
          : (mailboxDriver?.default_auth_mode || mailboxDriver?.auth_modes?.[0]?.value || ''),
      }
      next.captcha = {
        ...next.captcha,
        driver_type: captchaDriver?.driver_type || '',
        auth_mode: captchaDriver?.auth_modes?.some(mode => mode.value === next.captcha.auth_mode)
          ? next.captcha.auth_mode
          : (captchaDriver?.default_auth_mode || captchaDriver?.auth_modes?.[0]?.value || ''),
      }
      return next
    })
  }, [mailboxDrivers, captchaDrivers])

  const getErrorMessage = (error: unknown, fallback: string) => {
    if (error instanceof Error && error.message) {
      return error.message
    }
    return fallback
  }

  const updateProviderDefinitionForm = (providerType: ProviderType, key: string, value: any) => {
    setProviderDefinitionForm(current => {
      const next = {
        ...current,
        [providerType]: {
          ...current[providerType],
          [key]: value,
        },
      }
      if (key === 'driver_type') {
        const drivers = providerType === 'mailbox' ? mailboxDrivers : captchaDrivers
        const driver = drivers.find(item => item.driver_type === value) || null
        next[providerType].auth_mode = driver?.default_auth_mode || driver?.auth_modes?.[0]?.value || ''
        next[providerType].config = {}
        next[providerType].auth = {}
      }
      return next
    })
  }

  const updateProviderSetting = (providerType: ProviderType, providerKey: string, updater: (item: ProviderSetting) => ProviderSetting) => {
    setProviderSettings(current => ({
      ...current,
      [providerType]: current[providerType].map(item => item.provider_key === providerKey ? updater(item) : item),
    }))
  }

  const updateProviderSettingField = (providerType: ProviderType, providerKey: string, field: any, value: string) => {
    updateProviderSetting(providerType, providerKey, item => {
      if (field.category === 'auth') {
        return { ...item, auth: { ...item.auth, [field.key]: value } }
      }
      return { ...item, config: { ...item.config, [field.key]: value } }
    })
  }

  const markProviderDefault = (providerType: ProviderType, providerKey: string) => {
    setProviderSettings(current => ({
      ...current,
      [providerType]: current[providerType].map(item => ({
        ...item,
        is_default: item.provider_key === providerKey,
      })),
    }))
  }

  const persistProviderDefault = async (providerType: ProviderType, item: ProviderSetting) => {
    markProviderDefault(providerType, item.provider_key)
    await saveProviderSetting(providerType, {
      ...item,
      is_default: true,
    })
  }

  const saveProviderSetting = async (providerType: ProviderType, item: ProviderSetting) => {
    const stateKey = `${providerType}:${item.provider_key}`
    setProviderSaving(current => ({ ...current, [stateKey]: true }))
    setProviderError(current => ({ ...current, [providerType]: '' }))
    try {
      await apiFetch('/provider-settings', {
        method: 'PUT',
        body: JSON.stringify({
          id: item.id || undefined,
          provider_type: providerType,
          provider_key: item.provider_key,
          display_name: item.display_name,
          auth_mode: item.auth_mode,
          enabled: item.enabled,
          is_default: item.is_default,
          config: item.config,
          auth: item.auth,
          metadata: item.metadata || {},
        }),
      })
      invalidateConfigOptionsCache()
      invalidateConfigCache()
      await loadConfigData()
      setProviderNotice(current => ({ ...current, [providerType]: `已保存 ${item.catalog_label || item.provider_key} 配置` }))
      setProviderSaved(current => ({ ...current, [stateKey]: true }))
      setTimeout(() => setProviderSaved(current => ({ ...current, [stateKey]: false })), 2000)
    } catch (error) {
      setProviderError(current => ({ ...current, [providerType]: getErrorMessage(error, '保存 provider 配置失败') }))
    } finally {
      setProviderSaving(current => ({ ...current, [stateKey]: false }))
    }
  }

  const createProviderSetting = async (providerType: ProviderType, providerKey: string) => {
    if (!providerKey) return
    const catalog = (providerType === 'mailbox' ? mailboxCatalog : captchaCatalog).find(item => item.value === providerKey)
    if (!catalog) return
    const existing = providerSettings[providerType].some(item => item.provider_key === providerKey)
    if (existing) {
      setProviderDialog({ providerType, providerKey, readOnly: false })
      return
    }
    const stateKey = `${providerType}:${providerKey}`
    setProviderCreating(current => ({ ...current, [stateKey]: true }))
    setProviderError(current => ({ ...current, [providerType]: '' }))
    try {
      await apiFetch('/provider-settings', {
        method: 'POST',
        body: JSON.stringify({
          provider_type: providerType,
          provider_key: providerKey,
          display_name: catalog.label,
          auth_mode: catalog.default_auth_mode || catalog.auth_modes?.[0]?.value || '',
          enabled: true,
          is_default: providerSettings[providerType].length === 0,
          config: {},
          auth: {},
          metadata: {},
        }),
      })
      invalidateConfigOptionsCache()
      await loadConfigData()
      setProviderNotice(current => ({ ...current, [providerType]: `已新增 ${catalog.label}` }))
      setProviderAddDialog(null)
    } catch (error) {
      setProviderError(current => ({ ...current, [providerType]: getErrorMessage(error, '新增 provider 失败') }))
    } finally {
      setProviderCreating(current => ({ ...current, [stateKey]: false }))
    }
  }

  const createProviderDefinitionAndSetting = async (providerType: ProviderType) => {
    const payload = providerDefinitionForm[providerType]
    const driverList = providerType === 'mailbox' ? mailboxDrivers : captchaDrivers
    const driver = driverList.find(item => item.driver_type === payload.driver_type) || null
    const definitionKey = `${providerType}:${payload.provider_key || 'new'}`
    if (!payload.provider_key || !payload.label || !payload.driver_type) {
      setProviderError(current => ({ ...current, [providerType]: '请先填写 Provider 名称、Key 和驱动族' }))
      return
    }
    setProviderDefinitionCreating(current => ({ ...current, [definitionKey]: true }))
    setProviderError(current => ({ ...current, [providerType]: '' }))
    try {
      await apiFetch('/provider-definitions', {
        method: 'POST',
        body: JSON.stringify({
          provider_type: providerType,
          provider_key: payload.provider_key,
          label: payload.label,
          description: payload.description || '',
          driver_type: payload.driver_type,
          enabled: true,
          default_auth_mode: payload.auth_mode || driver?.default_auth_mode || '',
          metadata: {},
        }),
      })
      await apiFetch('/provider-settings', {
        method: 'POST',
        body: JSON.stringify({
          provider_type: providerType,
          provider_key: payload.provider_key,
          display_name: payload.label,
          auth_mode: payload.auth_mode || driver?.default_auth_mode || '',
          enabled: true,
          is_default: providerSettings[providerType].length === 0,
          config: payload.config || {},
          auth: payload.auth || {},
          metadata: {},
        }),
      })
      invalidateConfigOptionsCache()
      await loadConfigData()
      setProviderNotice(current => ({ ...current, [providerType]: `已创建动态 provider ${payload.label}` }))
      setProviderCreateDialog(null)
      setProviderDefinitionForm(current => ({
        ...current,
        [providerType]: {
          provider_key: '',
          label: '',
          description: '',
          driver_type: driver?.driver_type || '',
          auth_mode: driver?.default_auth_mode || driver?.auth_modes?.[0]?.value || '',
          config: {},
          auth: {},
        },
      }))
    } catch (error) {
      setProviderError(current => ({ ...current, [providerType]: getErrorMessage(error, '创建动态 provider 失败') }))
    } finally {
      setProviderDefinitionCreating(current => ({ ...current, [definitionKey]: false }))
    }
  }

  const deleteProviderSetting = async (providerType: ProviderType, item: ProviderSetting) => {
    const stateKey = `${providerType}:${item.provider_key}`
    setProviderDeleting(current => ({ ...current, [stateKey]: true }))
    setProviderError(current => ({ ...current, [providerType]: '' }))
    try {
      await apiFetch(`/provider-settings/${item.id}`, { method: 'DELETE' })
      invalidateConfigOptionsCache()
      await loadConfigData()
      setProviderNotice(current => ({ ...current, [providerType]: `已删除 ${item.catalog_label || item.provider_key}` }))
    } catch (error) {
      setProviderError(current => ({ ...current, [providerType]: getErrorMessage(error, '删除 provider 失败') }))
    } finally {
      setProviderDeleting(current => ({ ...current, [stateKey]: false }))
    }
  }

  const dialogItem = providerDialog.providerType
    ? providerSettings[providerDialog.providerType].find(item => item.provider_key === providerDialog.providerKey) || null
    : null
  const openProviderDialog = (providerType: ProviderType, providerKey: string, readOnly: boolean) => {
    setProviderDialog({ providerType, providerKey, readOnly })
  }

  const mailboxCount = providerSettings.mailbox.length
  const captchaCount = providerSettings.captcha.length
  const solverLabel = solverRunning === null ? '检测中' : solverRunning ? '运行中' : '未运行'
  const currentTabMeta = TABS.find(item => item.id === activeTab) ?? TABS[0]

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden p-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold text-[var(--text-primary)]">配置</div>
            <Badge variant="default">{currentTabMeta.label}</Badge>
            <Badge variant={solverRunning ? 'success' : solverRunning === false ? 'danger' : 'secondary'}>{solverLabel}</Badge>
          </div>
        </div>
      </Card>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <SettingsMetric label="邮箱服务" value={mailboxCount} icon={Mail} />
        <SettingsMetric label="验证码服务" value={captchaCount} icon={Shield} />
        <SettingsMetric label="求解器" value={solverLabel} icon={Orbit} />
        <SettingsMetric label="模块" value={TABS.length} icon={Package2} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[240px_minmax(0,1fr)]">
        <Card className="h-fit bg-[var(--bg-pane)]/60 xl:sticky xl:top-4">
          <div className="space-y-4">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">模块</div>
              <div className="mt-2 text-sm font-medium text-[var(--text-primary)]">选择要操作的控制面板</div>
            </div>
            <div className="space-y-1.5">
              {TABS.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setActiveTab(id)}
                  className={cn(
                    'w-full rounded-2xl border px-3 py-3 text-left transition-colors',
                    activeTab === id
                      ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--text-primary)]'
                      : 'border-transparent text-[var(--text-muted)] hover:border-[var(--border)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]'
                  )}
                >
                  <div className="flex items-center gap-2.5">
                    <Icon className={cn('h-4 w-4', activeTab === id ? 'text-[var(--accent)]' : 'text-[var(--text-muted)]')} />
                    <span className="text-sm font-medium">{label}</span>
                  </div>
                </button>
              ))}
            </div>

            <div className="rounded-[22px] border border-[var(--border-soft)] bg-[var(--chip-bg)] p-4">
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
                <Sparkles className="h-3.5 w-3.5" />
                求解器
              </div>
              <div className="mt-3 flex items-center gap-2">
                {solverRunning === null
                  ? <RefreshCw className="h-3.5 w-3.5 animate-spin text-[var(--text-muted)]" />
                  : solverRunning
                    ? <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
                    : <XCircle className="h-3.5 w-3.5 text-red-400" />}
                <span className={cn('text-sm font-medium', solverRunning ? 'text-emerald-400' : 'text-[var(--text-secondary)]')}>
                  {solverLabel}
                </span>
              </div>
              <Button variant="outline" size="sm" onClick={restartSolver} className="mt-4 w-full">
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                重启 Solver
              </Button>
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          {activeTab === 'platform_caps' ? (
            <PlatformCapsTab />
          ) : (
            <>
              {activeTab === 'register' && (
                <div className="rounded-[22px] border border-[var(--accent-edge)] bg-[var(--accent-soft)] px-4 py-3 text-sm text-[var(--text-secondary)]">
                  普通使用者只需要理解两件事：注册身份选“系统邮箱”还是“第三方账号”，执行方式选“协议模式 / 后台浏览器自动 / 可视浏览器自动”。这里的配置只是设置默认值。
                </div>
              )}
              {activeTab === 'mailbox' && (
                <>
                  {optionsError && (
                    <div className="rounded-[22px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                      {optionsError}
                    </div>
                  )}
                  {providerError.mailbox && (
                    <div className="rounded-[22px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                      {providerError.mailbox}
                    </div>
                  )}
                  {providerNotice.mailbox && !providerError.mailbox && (
                    <div className="rounded-[22px] border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
                      {providerNotice.mailbox}
                    </div>
                  )}
                  <div className="rounded-[22px] border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-[var(--text-secondary)]">
                    只有在注册身份选择“系统邮箱”时，才会使用这里的邮箱服务配置。列表行内可以直接查看详情、编辑、设默认和删除。
                  </div>
                  <div className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-pane)]/56 p-5 space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-[var(--text-primary)]">邮箱 Provider 列表</h3>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5">{providerSettings.mailbox.length} 个配置，支持查看详情、编辑、设默认、删除。</p>
                      </div>
                      <div className="flex items-center gap-3">
                        {unusedMailboxProviders.length === 0 ? (
                          <span className="text-xs text-[var(--text-muted)]">当前没有可新增的邮箱 provider</span>
                        ) : (
                          <span className="text-xs text-[var(--text-muted)]">还有 {unusedMailboxProviders.length} 个邮箱 provider 可新增</span>
                        )}
                        <Button size="sm" variant="outline" onClick={() => setProviderCreateDialog('mailbox')}>
                          <Plus className="h-3.5 w-3.5 mr-1" />
                          新建动态 Provider
                        </Button>
                        <Button size="sm" onClick={() => setProviderAddDialog('mailbox')}>
                          <Plus className="h-3.5 w-3.5 mr-1" />
                          新增 Provider
                        </Button>
                      </div>
                    </div>
                    {providerSettings.mailbox.length === 0 ? (
                      <div className="empty-state-panel">
                        当前没有邮箱 provider 配置，请先新增一个 provider。
                      </div>
                    ) : (
                      <div className="glass-table-wrap rounded-xl border border-[var(--border)]">
                        <table className="w-full min-w-[980px] text-sm">
                          <thead>
                            <tr className="border-b border-[var(--border)] bg-[var(--bg-hover)] text-xs text-[var(--text-muted)]">
                              <th className="px-4 py-3 text-left">名称</th>
                              <th className="px-4 py-3 text-left">Provider Key</th>
                              <th className="px-4 py-3 text-left">认证方式</th>
                              <th className="px-4 py-3 text-left">默认</th>
                              <th className="px-4 py-3 text-left">操作</th>
                            </tr>
                          </thead>
                          <tbody>
                            {providerSettings.mailbox.map(provider => {
                              const stateKey = `mailbox:${provider.provider_key}`
                              return (
                                <tr key={provider.provider_key} className="border-b border-[var(--border)]/50 hover:bg-[var(--bg-hover)]/60 transition-colors">
                                  <td className="px-4 py-3 whitespace-nowrap">
                                    <span className="font-medium text-[var(--text-primary)]">{provider.display_name || provider.catalog_label}</span>
                                    {provider.display_name && provider.display_name !== provider.catalog_label ? (
                                      <span className="ml-2 text-[11px] text-[var(--text-muted)]">({provider.catalog_label})</span>
                                    ) : null}
                                  </td>
                                  <td className="px-4 py-3 whitespace-nowrap text-[var(--text-secondary)]">{provider.provider_key}</td>
                                  <td className="px-4 py-3 whitespace-nowrap text-[var(--text-secondary)]">{provider.auth_modes.find(mode => mode.value === provider.auth_mode)?.label || provider.auth_mode || '-'}</td>
                                  <td className="px-4 py-3 whitespace-nowrap">
                                    {provider.is_default ? <span className="inline-flex rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-300">默认</span> : <span className="text-[var(--text-muted)]">-</span>}
                                  </td>
                                  <td className="px-4 py-3 whitespace-nowrap">
                                    <div className="flex items-center gap-2">
                                      <button onClick={() => openProviderDialog('mailbox', provider.provider_key, true)} className="table-action-btn">详情</button>
                                      <button onClick={() => openProviderDialog('mailbox', provider.provider_key, false)} className="table-action-btn">编辑</button>
                                      <button onClick={() => persistProviderDefault('mailbox', provider)} className="table-action-btn">
                                        {provider.is_default ? '当前默认' : '设默认'}
                                      </button>
                                      <button
                                        onClick={() => deleteProviderSetting('mailbox', provider)}
                                        disabled={providerDeleting[stateKey]}
                                        className="table-action-btn table-action-btn-danger"
                                      >
                                        {providerDeleting[stateKey] ? '删除中...' : '删除'}
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </>
              )}
              {activeTab === 'captcha' && (
                <>
                  {optionsError && (
                    <div className="rounded-[22px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                      {optionsError}
                    </div>
                  )}
                  {providerError.captcha && (
                    <div className="rounded-[22px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                      {providerError.captcha}
                    </div>
                  )}
                  {providerNotice.captcha && !providerError.captcha && (
                    <div className="rounded-[22px] border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
                      {providerNotice.captcha}
                    </div>
                  )}
                  <div className="rounded-[22px] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-[var(--text-secondary)]">
                    协议模式会按后端策略自动选择第一个已配置好的远程打码服务；浏览器模式固定走本地 Solver。列表行内可以直接查看详情、编辑、设默认、删除。
                  </div>
                  <div className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-pane)]/56 p-5">
                    <div className="mb-2">
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">当前策略</h3>
                    </div>
                    <div className="text-sm text-[var(--text-secondary)]">{getCaptchaStrategyLabel('protocol', configOptions.captcha_policy, configOptions.captcha_providers)}</div>
                    <div className="text-sm text-[var(--text-secondary)] mt-2">{getCaptchaStrategyLabel('headless', configOptions.captcha_policy, configOptions.captcha_providers)}</div>
                  </div>
                  <div className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-pane)]/56 p-5 space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-[var(--text-primary)]">验证 Provider 列表</h3>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5">{providerSettings.captcha.length} 个配置，协议模式会依次读取这里的可用项。</p>
                      </div>
                      <div className="flex items-center gap-3">
                        {unusedCaptchaProviders.length === 0 ? (
                          <span className="text-xs text-[var(--text-muted)]">当前没有可新增的验证 provider</span>
                        ) : (
                          <span className="text-xs text-[var(--text-muted)]">还有 {unusedCaptchaProviders.length} 个验证 provider 可新增</span>
                        )}
                        <Button size="sm" variant="outline" onClick={() => setProviderCreateDialog('captcha')}>
                          <Plus className="h-3.5 w-3.5 mr-1" />
                          新建动态 Provider
                        </Button>
                        <Button size="sm" onClick={() => setProviderAddDialog('captcha')}>
                          <Plus className="h-3.5 w-3.5 mr-1" />
                          新增 Provider
                        </Button>
                      </div>
                    </div>
                    {providerSettings.captcha.length === 0 ? (
                      <div className="empty-state-panel">
                        当前没有验证 provider 配置，请先新增一个 provider。
                      </div>
                    ) : (
                      <div className="glass-table-wrap rounded-xl border border-[var(--border)]">
                        <table className="w-full min-w-[980px] text-sm">
                          <thead>
                            <tr className="border-b border-[var(--border)] bg-[var(--bg-hover)] text-xs text-[var(--text-muted)]">
                              <th className="px-4 py-3 text-left">名称</th>
                              <th className="px-4 py-3 text-left">Provider Key</th>
                              <th className="px-4 py-3 text-left">认证方式</th>
                              <th className="px-4 py-3 text-left">默认</th>
                              <th className="px-4 py-3 text-left">操作</th>
                            </tr>
                          </thead>
                          <tbody>
                            {providerSettings.captcha.map(provider => {
                              const stateKey = `captcha:${provider.provider_key}`
                              return (
                                <tr key={provider.provider_key} className="border-b border-[var(--border)]/50 hover:bg-[var(--bg-hover)]/60 transition-colors">
                                  <td className="px-4 py-3 whitespace-nowrap">
                                    <span className="font-medium text-[var(--text-primary)]">{provider.display_name || provider.catalog_label}</span>
                                    {provider.display_name && provider.display_name !== provider.catalog_label ? (
                                      <span className="ml-2 text-[11px] text-[var(--text-muted)]">({provider.catalog_label})</span>
                                    ) : null}
                                  </td>
                                  <td className="px-4 py-3 whitespace-nowrap text-[var(--text-secondary)]">{provider.provider_key}</td>
                                  <td className="px-4 py-3 whitespace-nowrap text-[var(--text-secondary)]">{provider.auth_modes.find(mode => mode.value === provider.auth_mode)?.label || provider.auth_mode || '-'}</td>
                                  <td className="px-4 py-3 whitespace-nowrap">
                                    {provider.is_default ? <span className="inline-flex rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-300">默认</span> : <span className="text-[var(--text-muted)]">-</span>}
                                  </td>
                                  <td className="px-4 py-3 whitespace-nowrap">
                                    <div className="flex items-center gap-2">
                                      <button onClick={() => openProviderDialog('captcha', provider.provider_key, true)} className="table-action-btn">详情</button>
                                      <button onClick={() => openProviderDialog('captcha', provider.provider_key, false)} className="table-action-btn">编辑</button>
                                      <button onClick={() => persistProviderDefault('captcha', provider)} className="table-action-btn">
                                        {provider.is_default ? '当前默认' : '设默认'}
                                      </button>
                                      <button
                                        onClick={() => deleteProviderSetting('captcha', provider)}
                                        disabled={providerDeleting[stateKey]}
                                        className="table-action-btn table-action-btn-danger"
                                      >
                                        {providerDeleting[stateKey] ? '删除中...' : '删除'}
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </>
              )}
              {activeTab !== 'mailbox' && activeTab !== 'captcha' && sections.map(({ section, desc, items }) => (
                <div key={section} className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-pane)]/56 p-5">
                  <div className="mb-4">
                    <h3 className="text-sm font-semibold text-[var(--text-primary)]">{section}</h3>
                    {desc && <p className="text-xs text-[var(--text-muted)] mt-0.5">{desc}</p>}
                  </div>
                  {items.map((field: any) => (
                    <Field key={field.key} field={field} form={form} setForm={setForm}
                      showSecret={showSecret} setShowSecret={setShowSecret} />
                  ))}
                </div>
              ))}
              {activeTab !== 'mailbox' && activeTab !== 'captcha' && (
                <Button onClick={save} disabled={saving} className="w-full">
                  <Save className="h-4 w-4 mr-2" />
                  {saved ? '已保存 ✓' : saving ? '保存中...' : '保存配置'}
                </Button>
              )}
            </>
          )}
        </div>
      </div>
      {providerDialog.providerType && dialogItem && (
        <ProviderDetailModal
          title={providerDialog.providerType === 'mailbox' ? '邮箱 Provider 详情' : '验证 Provider 详情'}
          item={dialogItem}
          readOnly={providerDialog.readOnly}
          saving={providerSaving[`${providerDialog.providerType}:${dialogItem.provider_key}`]}
          saved={providerSaved[`${providerDialog.providerType}:${dialogItem.provider_key}`]}
          showSecret={showSecret}
          setShowSecret={setShowSecret}
          onClose={() => setProviderDialog({ providerType: null, providerKey: '', readOnly: false })}
          onEdit={() => setProviderDialog(current => ({ ...current, readOnly: false }))}
          onChangeName={(value: string) => updateProviderSetting(providerDialog.providerType as ProviderType, dialogItem.provider_key, item => ({ ...item, display_name: value }))}
          onChangeAuthMode={(value: string) => updateProviderSetting(providerDialog.providerType as ProviderType, dialogItem.provider_key, item => ({ ...item, auth_mode: value }))}
          onChangeField={(field: any, value: string) => updateProviderSettingField(providerDialog.providerType as ProviderType, dialogItem.provider_key, field, value)}
          onSave={() => saveProviderSetting(providerDialog.providerType as ProviderType, dialogItem)}
        />
      )}
      {providerAddDialog && (
        <AddProviderModal
          title={providerAddDialog === 'mailbox' ? '新增邮箱 Provider' : '新增验证 Provider'}
          providerType={providerAddDialog}
          providers={providerAddDialog === 'mailbox' ? unusedMailboxProviders : unusedCaptchaProviders}
          selectedKey={newProviderKey[providerAddDialog]}
          creating={Boolean(newProviderKey[providerAddDialog] && providerCreating[`${providerAddDialog}:${newProviderKey[providerAddDialog]}`])}
          onSelect={(value: string) => setNewProviderKey(current => ({ ...current, [providerAddDialog]: value }))}
          onClose={() => setProviderAddDialog(null)}
          onCreate={(providerKey: string) => createProviderSetting(providerAddDialog, providerKey)}
        />
      )}
      {providerCreateDialog && (
        <CreateProviderDefinitionModal
          title={providerCreateDialog === 'mailbox' ? '新建动态邮箱 Provider' : '新建动态验证 Provider'}
          providerType={providerCreateDialog}
          drivers={providerCreateDialog === 'mailbox' ? mailboxDrivers : captchaDrivers}
          form={providerDefinitionForm[providerCreateDialog]}
          creating={Boolean(providerDefinitionCreating[`${providerCreateDialog}:${providerDefinitionForm[providerCreateDialog].provider_key || 'new'}`])}
          showSecret={showSecret}
          setShowSecret={setShowSecret}
          onChange={(key: string, value: any) => updateProviderDefinitionForm(providerCreateDialog, key, value)}
          onClose={() => setProviderCreateDialog(null)}
          onCreate={() => createProviderDefinitionAndSetting(providerCreateDialog)}
        />
      )}
    </div>
  )
}
