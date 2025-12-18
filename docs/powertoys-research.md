# Microsoft PowerToys 深度调研报告

> 调研时间：2024年12月
> 目的：为 RPA/效率工具开发提供参考借鉴

---

## 一、项目概况

| 项目 | 信息 |
|------|------|
| GitHub | [microsoft/PowerToys](https://github.com/microsoft/PowerToys) |
| Stars | 115k+ |
| 开源协议 | MIT |
| 开发语言 | C#, C++, XAML |
| 系统要求 | Windows 10 2004+ / Windows 11 |
| 官方文档 | [Microsoft Learn](https://learn.microsoft.com/zh-cn/windows/powertoys/) |

---

## 二、完整功能模块列表（30+）

### 2.1 窗口管理类

| 模块 | 快捷键 | 功能 |
|------|--------|------|
| **FancyZones** | `Win+Shift+`` | 窗口布局管理器，可自定义网格布局 |
| **Always On Top** | `Win+Ctrl+T` | 窗口置顶 |
| **Crop and Lock** | - | 裁剪窗口为独立可交互小窗口 |
| **Peek** | `Ctrl+Space` | 快速预览文件内容 |
| **Workspaces** | - | 工作区管理，一键恢复窗口布局 |

### 2.2 键盘与输入类

| 模块 | 快捷键 | 功能 |
|------|--------|------|
| **Keyboard Manager** | - | 按键重映射、快捷键自定义 |
| **Shortcut Guide** | `Win+Shift+/` | 显示当前可用的 Windows 快捷键 |
| **Quick Accent** | 长按字母键 | 快速输入带重音字符（如 é, ñ） |

### 2.3 鼠标工具类

| 模块 | 功能 |
|------|------|
| **Find My Mouse** | 双击 Ctrl 高亮鼠标位置 |
| **Mouse Highlighter** | 点击时高亮显示 |
| **Mouse Jump** | 大屏幕快速移动鼠标 |
| **Mouse Pointer Crosshairs** | 十字准星定位 |
| **Mouse Without Borders** | 多台电脑共享鼠标键盘 |

### 2.4 搜索启动类

| 模块 | 快捷键 | 功能 |
|------|--------|------|
| **PowerToys Run** | `Alt+Space` | 全局搜索启动器（类似 macOS Spotlight） |
| **Command Palette** | 可配置 | PowerToys Run 的下一代版本 |

### 2.5 剪贴板与文本类

| 模块 | 快捷键 | 功能 |
|------|--------|------|
| **Advanced Paste** | `Win+Shift+V` | 智能粘贴（支持 AI 转换格式） |
| **Text Extractor** | `Win+Shift+T` | OCR 屏幕取字 |

### 2.6 文件工具类

| 模块 | 功能 |
|------|------|
| **File Explorer add-ons** | 文件预览增强（支持 .md, .svg, .pdf 等） |
| **File Locksmith** | 查看文件被哪个进程占用 |
| **Image Resizer** | 右键批量调整图片尺寸 |
| **PowerRename** | 批量重命名（支持正则表达式） |

### 2.7 系统工具类

| 模块 | 快捷键 | 功能 |
|------|--------|------|
| **Awake** | - | 保持电脑唤醒（防止休眠） |
| **Color Picker** | `Win+Shift+C` | 屏幕取色器 |
| **Environment Variables** | - | 环境变量管理器 |
| **Hosts File Editor** | - | hosts 文件可视化编辑 |
| **Registry Preview** | - | 注册表文件预览编辑 |
| **Screen Ruler** | `Win+Shift+M` | 屏幕像素测量 |
| **ZoomIt** | - | 屏幕缩放/标注/录制（演示神器） |

---

## 三、架构设计分析

### 3.1 整体架构

```
PowerToys
├── PowerToys.exe          # 主进程/托盘管理
├── Settings UI            # WinUI 3 设置界面
├── Modules/               # 各功能模块
│   ├── FancyZones/
│   ├── PowerToys Run/
│   ├── Keyboard Manager/
│   └── ...
└── Common/                # 公共库
```

### 3.2 模块化设计特点

1. **独立进程**：每个模块可独立启用/禁用
2. **统一设置中心**：所有模块配置集中管理
3. **低级键盘钩子**：通过 Windows Hook 实现全局快捷键
4. **托盘常驻**：后台运行，按需激活

### 3.3 技术栈

- **UI 框架**：WinUI 3 / XAML
- **后端语言**：C# (.NET)
- **底层模块**：C++ (性能敏感部分)
- **配置存储**：JSON 文件
- **进程通信**：Named Pipes

---

## 四、PowerToys Run 插件系统

### 4.1 插件目录结构

```
Plugin/
├── plugin.json          # 插件元数据
├── Main.cs              # 实现 IPlugin 接口
├── Images/              # 图标资源
└── *.dll                # 编译产物
```

### 4.2 plugin.json 示例

```json
{
  "ID": "YOUR_GUID_HERE",
  "ActionKeyword": "demo",
  "Name": "Demo Plugin",
  "Author": "Your Name",
  "Version": "1.0.0",
  "Language": "csharp",
  "Website": "https://github.com/...",
  "ExecuteFileName": "YourPlugin.dll",
  "IsGlobal": false,
  "IcoPathDark": "Images\\icon.dark.png",
  "IcoPathLight": "Images\\icon.light.png"
}
```

### 4.3 核心接口（C#）

```csharp
// 必须实现的主接口
public interface IPlugin
{
    string Name { get; }
    string Description { get; }

    // 初始化方法
    void Init(PluginInitContext context);

    // 查询方法 - 用户输入时调用
    List<Result> Query(Query query);
}

// 可选接口
public interface IContextMenu           // 右键菜单
public interface ISettingProvider       // 设置面板
public interface IPluginI18n            // 国际化支持
public interface IDelayedExecutionPlugin // 延迟执行（防抖）
public interface IDisposable            // 资源清理
```

### 4.4 Query 方法详解

```csharp
public List<Result> Query(Query query)
{
    var results = new List<Result>();

    // query.Search - 用户输入的搜索词
    // query.ActionKeyword - 触发关键词

    results.Add(new Result
    {
        Title = "结果标题",
        SubTitle = "结果描述",
        IcoPath = "Images/icon.png",
        Score = 100,  // 排序权重
        Action = context =>
        {
            // 用户选择该结果时执行的动作
            Process.Start("notepad.exe");
            return true;  // true 表示关闭搜索框
        }
    });

    return results;
}
```

### 4.5 插件安装路径

```
%LOCALAPPDATA%\Microsoft\PowerToys\PowerToys Run\Plugins\
```

### 4.6 社区插件生态

已有 60+ 社区插件，参考：[awesome-powertoys-run-plugins](https://github.com/hlaueriksson/awesome-powertoys-run-plugins)

热门插件：
- Everything 文件搜索集成
- GitHub 仓库搜索
- VS Code 工作区
- Docker 容器管理
- 密码生成器
- 翻译插件

---

## 五、Keyboard Manager 详解

### 5.1 功能类型

| 类型 | 示例 | 说明 |
|------|------|------|
| **重映射按键** | A → B | 按 A 输出 B |
| **重映射快捷键** | Ctrl+C → Win+C | 快捷键替换 |
| **按键到快捷键** | CapsLock → Ctrl+Shift | 单键触发组合键 |
| **快捷键到按键** | Ctrl+Q → Esc | 组合键简化 |
| **应用级映射** | 仅在 VSCode 生效 | 上下文感知 |

### 5.2 实现原理

- 使用 Windows 低级键盘钩子 (`SetWindowsHookEx`)
- 拦截键盘输入 → 判断映射规则 → 发送新按键
- 支持应用级别过滤（通过进程名匹配）

### 5.3 限制

- `Win+L`（锁屏）和 `Ctrl+Alt+Del` 无法重映射（系统保留）
- `Fn` 键通常无法重映射（硬件级别）
- 需要管理员权限才能影响提权窗口

---

## 六、Advanced Paste (高级粘贴)

### 6.1 功能特性

- 纯文本粘贴
- Markdown → HTML
- JSON 格式化
- **AI 转换**（需配置 API Key）

### 6.2 支持的 AI 服务

- OpenAI
- Azure OpenAI
- Google Gemini
- Mistral
- Ollama（本地）
- Foundry Local

### 6.3 AI 转换示例

用户复制表格数据 → `Win+Shift+V` → 选择 "AI 转换" → 输入 "转成 Markdown 表格"

---

## 七、其他效率工具对比

| 工具 | 平台 | 特点 | 价格 |
|------|------|------|------|
| **PowerToys** | Windows | 微软官方，功能全面 | 免费开源 |
| **Quicker** | Windows | 鼠标友好，动作库丰富 | ¥60/年 |
| **uTools** | 跨平台 | 插件生态，国产 | 部分免费 |
| **AutoHotkey** | Windows | 脚本灵活，学习曲线高 | 免费开源 |
| **Raycast** | macOS | 键盘优先，AI 集成 | 基础免费 |
| **Alfred** | macOS | 成熟稳定，工作流强大 | $34 起 |
| **Keyboard Maestro** | macOS | 自动化标杆 | $36 |

---

## 八、可借鉴的设计要点

### 8.1 模块化架构
- 每个功能独立模块，可单独启用/禁用
- 模块间不互相影响
- 便于扩展和维护

### 8.2 统一快捷键管理
- 集中配置所有快捷键
- 冲突检测机制
- 支持应用级别作用域

### 8.3 插件系统
- 清晰的接口定义
- 完善的开发文档
- NuGet 包简化依赖
- 社区生态繁荣

### 8.4 低侵入性
- 托盘后台运行
- 按需激活，不占用资源
- 无广告无打扰

### 8.5 配置管理
- JSON 配置文件，人类可读
- 支持导入导出
- 配置路径固定，便于同步

---

## 九、与 AI Agent 系统结合建议

### 9.1 架构设计

```
┌────────────────────────────────────────────────────┐
│              用户快捷键/语音/文字                   │
└─────────────────────┬──────────────────────────────┘
                      ▼
┌────────────────────────────────────────────────────┐
│          快捷键服务 (类 PowerToys)                  │
│  - 全局热键监听                                     │
│  - 快捷键 → 动作映射                               │
│  - 上下文感知（当前应用）                           │
└─────────────────────┬──────────────────────────────┘
                      ▼
┌────────────────────────────────────────────────────┐
│              MCP Gateway / Agent                    │
│  - 自然语言理解                                     │
│  - 工具调用 (MCP Servers)                          │
│  - 流程编排                                         │
└────────────────────────────────────────────────────┘
```

### 9.2 差异化方向

| 维度 | PowerToys | AI Agent 效率工具 |
|------|-----------|------------------|
| 触发方式 | 快捷键 → 固定动作 | 快捷键 → LLM → 智能动作 |
| 配置方式 | GUI 配置 | 自然语言定义 |
| 适应性 | 固定流程 | 动态推断 |
| 学习能力 | 无 | 可学习用户习惯 |

### 9.3 可实现的场景

1. `Win+Q` 唤起 → 输入「帮我把这个 Excel 整理成图表」→ Agent 自动执行
2. 选中文本 + `Ctrl+Alt+T` → 自动翻译并替换
3. 截图 + `Ctrl+Alt+O` → OCR 识别 + AI 理解内容
4. `Win+Alt+M` → 「帮我整理会议纪要」→ 自动汇总剪贴板内容

---

## 十、参考资源

### 官方资源
- [Microsoft Learn - PowerToys 文档](https://learn.microsoft.com/zh-cn/windows/powertoys/)
- [GitHub - microsoft/PowerToys](https://github.com/microsoft/PowerToys)
- [PowerToys Run Plugin Spec](https://github.com/microsoft/PowerToys/wiki/PowerToys-Run-Plugin-spec)
- [PowerToys Releases](https://github.com/microsoft/powertoys/releases/)

### 开发资源
- [PowerToys Run 插件开发入门](https://zhuanlan.zhihu.com/p/9424879098)
- [awesome-powertoys-run-plugins](https://github.com/hlaueriksson/awesome-powertoys-run-plugins)
- [Demo 插件源码](https://github.com/hlaueriksson/ConductOfCode/tree/master/PowerToysRun)

### 相关文章
- [少数派 - PowerToys 使用指南](https://sspai.com/post/74979)
- [Keyboard Manager 官方文档](https://learn.microsoft.com/en-us/windows/powertoys/keyboard-manager)
- [Shortcut Guide 官方文档](https://learn.microsoft.com/en-us/windows/powertoys/shortcut-guide)
