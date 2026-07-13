const UI_DICTIONARY = [
  {
    page: 'Web · 页面结构与布局',
    items: [
      { name: '页头（Header）', desc: '页面顶部区域，通常放品牌、导航、搜索和账号入口。' },
      { name: '页脚（Footer）', desc: '页面底部区域，通常放版权、备案、帮助和辅助链接。' },
      { name: '主内容区（Main Content）', desc: '承载页面核心内容的主要区域。' },
      { name: '侧边栏（Sidebar）', desc: '位于页面一侧的导航、筛选或辅助信息区域。' },
      { name: '双栏布局（Two-column Layout）', desc: '将内容分成左右两列的页面布局。' },
      { name: '三栏布局（Three-column Layout）', desc: '常见于后台、邮箱和内容平台的三列布局。' },
      { name: '栅格布局（Grid Layout）', desc: '按规则的行列网格排列内容或卡片。' },
      { name: '弹性布局（Flex Layout）', desc: '按方向、间距和伸缩规则排列子元素。' },
      { name: '分栏（Columns）', desc: '将同一区域划分为多个并列内容栏。' },
      { name: '容器（Container）', desc: '约束内容宽度、边距和对齐方式的外层区域。' },
      { name: '分区（Section）', desc: '页面中具有独立主题的一段内容区域。' },
      { name: '面板（Panel）', desc: '组合展示一组相关信息或操作的区域。' },
      { name: '卡片（Card）', desc: '带独立边界的内容单元，常包含标题、正文和操作。' },
      { name: '折叠面板（Accordion）', desc: '可逐项展开或收起内容的纵向面板组。' },
      { name: '分隔线（Divider）', desc: '分隔不同内容区域的横线或竖线。' },
      { name: '留白/间距（Spacing）', desc: '组件之间的外边距、内边距或空白区域。' },
    ],
  },
  {
    page: 'Web · 导航与定位',
    items: [
      { name: '顶部导航栏（Navbar）', desc: '横向展示主要页面入口的导航区域。' },
      { name: '侧边导航（Side Navigation）', desc: '纵向排列页面或模块入口的导航区域。' },
      { name: '汉堡菜单（Hamburger Menu）', desc: '三横线图标触发的折叠导航菜单。' },
      { name: '面包屑（Breadcrumb）', desc: '显示当前页面在层级结构中所处位置的导航。' },
      { name: '选项卡（Tabs）', desc: '在同一区域切换多组并列内容。' },
      { name: '分段控件（Segmented Control）', desc: '用一组相邻按钮切换少量互斥视图或状态。' },
      { name: '下拉菜单（Dropdown Menu）', desc: '点击触发器后展开的一组命令或选项。' },
      { name: '巨型菜单（Mega Menu）', desc: '可容纳多列分类和大量入口的大型下拉导航。' },
      { name: '上下文菜单（Context Menu）', desc: '右键或长按后在当前位置出现的操作菜单。' },
      { name: '锚点导航（Anchor Navigation）', desc: '跳转到当前长页面内指定章节的位置导航。' },
      { name: '分页器（Pagination）', desc: '在多页数据之间切换页码的控件。' },
      { name: '步骤条（Stepper/Steps）', desc: '显示流程步骤、当前位置和完成状态。' },
      { name: '返回顶部（Back to Top）', desc: '将长页面快速滚动到顶部的悬浮入口。' },
      { name: '链接（Link）', desc: '跳转到其他页面、位置或资源的文本入口。' },
    ],
  },
  {
    page: 'Web · 按钮与操作',
    items: [
      { name: '主按钮（Primary Button）', desc: '页面或区域中最重要的主要操作按钮。' },
      { name: '次按钮（Secondary Button）', desc: '重要性低于主操作的辅助按钮。' },
      { name: '文字按钮（Text Button）', desc: '没有明显边框或底色的轻量操作按钮。' },
      { name: '图标按钮（Icon Button）', desc: '仅以图标表达操作的按钮。' },
      { name: '幽灵按钮（Ghost Button）', desc: '透明背景、弱边框或弱对比度的按钮。' },
      { name: '危险按钮（Danger Button）', desc: '用于删除、清空等高风险操作的强调按钮。' },
      { name: '拆分按钮（Split Button）', desc: '主操作按钮与下拉更多操作组合在一起。' },
      { name: '按钮组（Button Group）', desc: '多个相关按钮紧邻排列形成的操作组。' },
      { name: '切换按钮（Toggle Button）', desc: '点击后在选中和未选中状态间切换。' },
      { name: '悬浮操作按钮（Floating Action Button）', desc: '浮在内容上方、用于突出主要操作的圆形按钮。' },
      { name: '复制按钮（Copy Button）', desc: '将文本、链接或代码复制到剪贴板。' },
      { name: '更多操作（More Actions）', desc: '通常以三点图标承载次要操作菜单。' },
      { name: '拖拽手柄（Drag Handle）', desc: '用于拖动排序、调整大小或移动对象的把手。' },
    ],
  },
  {
    page: 'Web · 表单与输入',
    items: [
      { name: '单行输入框（Text Field）', desc: '输入一行文本的基础表单控件。' },
      { name: '多行文本框（Textarea）', desc: '输入较长、多行文本的表单控件。' },
      { name: '密码输入框（Password Field）', desc: '隐藏或切换显示密码内容的输入框。' },
      { name: '搜索框（Search Box）', desc: '输入关键词并搜索内容的输入控件。' },
      { name: '数字输入框（Number Input）', desc: '输入数字并可带增减按钮的控件。' },
      { name: '下拉选择框（Select）', desc: '从展开的选项列表中选择一个值。' },
      { name: '多选选择器（Multi-select）', desc: '从选项列表中选择多个值。' },
      { name: '自动完成（Autocomplete）', desc: '输入时提供匹配建议并允许快速选择。' },
      { name: '级联选择器（Cascader）', desc: '按层级逐级选择地区、分类等数据。' },
      { name: '复选框（Checkbox）', desc: '独立选择或取消选择一个或多个选项。' },
      { name: '单选框（Radio Button）', desc: '从一组互斥选项中选择一个。' },
      { name: '开关（Switch）', desc: '在开启和关闭两种状态间切换。' },
      { name: '滑块（Slider）', desc: '在连续或分段范围内拖动选择数值。' },
      { name: '日期选择器（Date Picker）', desc: '选择单个日期的日历控件。' },
      { name: '日期范围选择器（Date Range Picker）', desc: '选择开始日期和结束日期。' },
      { name: '时间选择器（Time Picker）', desc: '选择小时、分钟或秒。' },
      { name: '颜色选择器（Color Picker）', desc: '通过色板、色相或色值选择颜色。' },
      { name: '文件上传（File Upload）', desc: '选择、拖拽并上传本地文件。' },
      { name: '拖拽上传区（Dropzone）', desc: '将文件拖入指定区域完成上传。' },
      { name: '验证码输入框（Verification Code）', desc: '输入短信、邮件或图形验证码。' },
      { name: '标签输入框（Tag Input）', desc: '输入并生成多个可删除标签。' },
      { name: '富文本编辑器（Rich Text Editor）', desc: '编辑带格式文本、图片和链接的输入区域。' },
      { name: '表单标签（Label）', desc: '说明输入项名称和用途的文字。' },
      { name: '帮助文字（Helper Text）', desc: '位于控件附近的格式提示或补充说明。' },
      { name: '错误提示（Validation Error）', desc: '表单校验失败时显示的原因和修正提示。' },
    ],
  },
  {
    page: 'Web · 数据展示',
    items: [
      { name: '数据表格（Data Table）', desc: '以行列形式展示结构化数据并支持操作。' },
      { name: '列表（List）', desc: '按纵向或横向顺序展示重复内容项。' },
      { name: '描述列表（Description List）', desc: '以字段名和值成对展示详情信息。' },
      { name: '树形控件（Tree View）', desc: '以可展开层级展示目录或组织结构。' },
      { name: '时间线（Timeline）', desc: '按时间顺序展示事件和状态变化。' },
      { name: '统计数值（Statistic）', desc: '突出展示关键数字、单位和变化趋势。' },
      { name: '徽标（Badge）', desc: '显示状态、数量或短标签的小型标记。' },
      { name: '标签（Tag/Chip）', desc: '表达分类、属性或可移除选项的紧凑元素。' },
      { name: '头像（Avatar）', desc: '展示用户或对象的图片、文字缩写或图标。' },
      { name: '头像组（Avatar Group）', desc: '紧凑展示多个用户头像和溢出数量。' },
      { name: '工具提示（Tooltip）', desc: '悬停或聚焦时显示的简短补充说明。' },
      { name: '气泡卡片（Popover）', desc: '由点击或悬停触发、可承载较丰富内容的浮层。' },
      { name: '代码块（Code Block）', desc: '以等宽字体和语法高亮展示代码。' },
      { name: '键值对（Key-value Pair）', desc: '并列展示属性名称和对应值。' },
      { name: '图片画廊（Gallery）', desc: '以网格、瀑布流或轮播形式展示多张图片。' },
      { name: '轮播图（Carousel）', desc: '在同一区域轮换展示多项内容或广告。' },
      { name: '图表（Chart）', desc: '用折线、柱状、饼图等方式可视化数据。' },
      { name: '进度条（Progress Bar）', desc: '用横向条形显示任务或数值进度。' },
      { name: '仪表盘（Dashboard）', desc: '组合关键指标、图表和状态概览的页面。' },
      { name: '空状态（Empty State）', desc: '没有数据时显示的说明、插图和引导操作。' },
      { name: '骨架屏（Skeleton）', desc: '内容加载期间模拟最终布局的占位元素。' },
    ],
  },
  {
    page: 'Web · 筛选、查询与排序',
    items: [
      { name: '筛选栏（Filter Bar）', desc: '集中放置查询条件和筛选操作的区域。' },
      { name: '筛选器（Filter）', desc: '按条件缩小当前数据范围的控件。' },
      { name: '高级筛选（Advanced Filter）', desc: '组合多个字段、运算符和条件的复杂筛选器。' },
      { name: '排序控件（Sort Control）', desc: '选择排序字段和升降序的控件。' },
      { name: '搜索建议（Search Suggestions）', desc: '输入关键词时展示的联想词或匹配结果。' },
      { name: '搜索结果页（Search Results）', desc: '集中展示关键词命中内容的页面。' },
      { name: '筛选标签（Filter Chip）', desc: '显示当前已生效条件并可快速移除。' },
      { name: '清除筛选（Clear Filters）', desc: '一次恢复全部筛选条件到默认值。' },
      { name: '列筛选（Column Filter）', desc: '针对表格某一列设置筛选条件。' },
      { name: '列排序（Column Sort）', desc: '点击表头按该列升序或降序排列。' },
      { name: '视图切换器（View Switcher）', desc: '在列表、网格、看板等展示方式间切换。' },
    ],
  },
  {
    page: 'Web · 反馈、状态与弹层',
    items: [
      { name: '模态对话框（Modal/Dialog）', desc: '覆盖页面并要求用户处理后才能继续的弹层。' },
      { name: '确认对话框（Confirm Dialog）', desc: '在执行重要或危险操作前请求确认。' },
      { name: '抽屉（Drawer）', desc: '从屏幕边缘滑出、承载详情或表单的面板。' },
      { name: '提示消息（Toast）', desc: '短暂出现并自动消失的轻量操作反馈。' },
      { name: '通知（Notification）', desc: '展示较完整消息并可包含操作的通知组件。' },
      { name: '警告提示（Alert）', desc: '固定展示成功、信息、警告或错误状态。' },
      { name: '横幅（Banner）', desc: '横跨页面或区域展示重要公告和行动入口。' },
      { name: '加载指示器（Spinner）', desc: '表示内容或操作正在加载的旋转图标。' },
      { name: '全屏加载遮罩（Loading Overlay）', desc: '阻止当前区域操作并显示加载状态的遮罩。' },
      { name: '操作结果页（Result Page）', desc: '集中展示成功、失败或异常结果及后续操作。' },
      { name: '错误页（Error Page）', desc: '展示 404、403、500 等错误及恢复入口。' },
      { name: '离线提示（Offline Indicator）', desc: '说明网络断开、重连中或仅可离线使用。' },
      { name: '未保存更改提示（Unsaved Changes）', desc: '离开页面前提醒仍有未保存内容。' },
    ],
  },
  {
    page: 'Web · 业务型复合组件',
    items: [
      { name: '登录表单（Login Form）', desc: '组合账号、密码、验证码和登录操作。' },
      { name: '注册表单（Registration Form）', desc: '组合账号创建、验证和协议确认字段。' },
      { name: '全局搜索（Global Search）', desc: '跨页面、模块或数据类型搜索内容。' },
      { name: '命令面板（Command Palette）', desc: '通过关键词快速查找并执行应用命令。' },
      { name: '数据看板（Kanban Board）', desc: '用多列卡片表达流程阶段并支持拖动。' },
      { name: '日历（Calendar）', desc: '按月、周或日展示日期和事件。' },
      { name: '日程表（Scheduler）', desc: '按时间段安排、拖动和调整日程。' },
      { name: '聊天窗口（Chat Window）', desc: '展示消息记录、输入区和会话操作。' },
      { name: '评论区（Comments）', desc: '展示评论、回复、提及和互动操作。' },
      { name: '文件管理器（File Manager）', desc: '以目录树或列表管理文件和文件夹。' },
      { name: '购物车（Shopping Cart）', desc: '汇总商品、数量、价格和结算操作。' },
      { name: '价格卡（Pricing Card）', desc: '展示套餐价格、权益和购买入口。' },
      { name: '引导流程（Onboarding）', desc: '帮助新用户完成介绍、配置或首次操作。' },
      { name: '新手引导（Product Tour）', desc: '用高亮、遮罩和说明逐步介绍界面。' },
    ],
  },
  {
    page: 'Android · 页面结构与导航',
    items: [
      { name: '状态栏（Status Bar）', desc: '屏幕顶部显示时间、网络、电量等系统状态。' },
      { name: '应用栏/顶部栏（App Bar/Top App Bar）', desc: '页面顶部放标题、返回和页面操作的区域。' },
      { name: '大标题顶部栏（Large Top App Bar）', desc: '滚动时可折叠的大标题应用栏。' },
      { name: '底部导航栏（Bottom Navigation）', desc: '在少量一级页面之间切换的底部导航。' },
      { name: '导航栏（Navigation Bar）', desc: 'Material 3 中承载多个一级目的地的底部控件。' },
      { name: '导航抽屉（Navigation Drawer）', desc: '从侧边滑出显示应用主要页面入口。' },
      { name: '导航轨道（Navigation Rail）', desc: '平板或横屏上使用的纵向一级导航。' },
      { name: '系统导航栏（System Navigation Bar）', desc: '屏幕底部的返回、主页、最近任务或手势区域。' },
      { name: '返回按钮（Back Button）', desc: '返回上一个页面或上一级层级。' },
      { name: '标签页（Tab Row）', desc: '在同一页面内切换并列内容。' },
      { name: '滚动标签栏（Scrollable Tab Row）', desc: '标签较多时可横向滚动的标签栏。' },
      { name: '页面指示器（Page Indicator）', desc: '显示轮播页或分页内容的当前位置。' },
      { name: '自适应双栏（List-detail Layout）', desc: '大屏上并列展示列表和详情的布局。' },
      { name: '脚手架布局（Scaffold）', desc: '统一组织顶部栏、底栏、悬浮按钮和内容区。' },
    ],
  },
  {
    page: 'Android · 布局与内容容器',
    items: [
      { name: '纵向布局（Column）', desc: '将子组件从上到下排列。' },
      { name: '横向布局（Row）', desc: '将子组件从左到右排列。' },
      { name: '层叠布局（Box）', desc: '允许子组件堆叠、对齐或覆盖。' },
      { name: '约束布局（ConstraintLayout）', desc: '通过组件间约束关系组织复杂界面。' },
      { name: '滚动容器（Scroll View）', desc: '让超出屏幕范围的单个内容区域滚动。' },
      { name: '懒加载列表（LazyColumn/RecyclerView）', desc: '高效展示可纵向滚动的大量重复条目。' },
      { name: '横向列表（LazyRow/Horizontal RecyclerView）', desc: '高效展示可横向滚动的重复条目。' },
      { name: '网格列表（Lazy Grid/GridLayout）', desc: '按多列网格展示大量条目。' },
      { name: '卡片（Card）', desc: '以独立表面组合展示内容和操作。' },
      { name: '列表项（List Item）', desc: '列表中的单行内容，可含图标、文字和操作。' },
      { name: '分隔线（Divider/Horizontal Divider）', desc: '分隔列表项或内容区域。' },
      { name: '表面（Surface）', desc: '承载背景色、形状、阴影和内容的基础容器。' },
      { name: '下拉刷新（Pull to Refresh）', desc: '下拉内容触发刷新数据。' },
      { name: '可展开列表项（Expandable Item）', desc: '点击后展开或收起详情内容的列表项。' },
      { name: '分页列表（Paging List）', desc: '滚动到末尾时分批加载更多数据的列表。' },
    ],
  },
  {
    page: 'Android · 文本、图像与数据展示',
    items: [
      { name: '文本（Text/TextView）', desc: '显示标题、正文、标签或说明文字。' },
      { name: '图标（Icon/ImageVector）', desc: '用矢量图形表达对象、状态或操作。' },
      { name: '图片（Image/ImageView）', desc: '显示位图、矢量图、网络图或资源图片。' },
      { name: '头像（Avatar）', desc: '以圆形或方形图片表示用户或对象。' },
      { name: '徽章（Badge）', desc: '在图标附近显示数量或状态提醒。' },
      { name: '辅助标签（Chip）', desc: '紧凑表达属性、筛选条件、输入或操作。' },
      { name: '筛选标签（Filter Chip）', desc: '在一组选项中选择一个或多个筛选条件。' },
      { name: '输入标签（Input Chip）', desc: '表示用户输入的实体并支持删除。' },
      { name: '建议标签（Suggestion Chip）', desc: '向用户提供推荐回复或下一步操作。' },
      { name: '轮播页（Pager）', desc: '通过左右滑动切换页面或内容卡。' },
      { name: '进度指示器（Progress Indicator）', desc: '显示确定或不确定的加载进度。' },
      { name: '圆形进度条（Circular Progress）', desc: '用圆环动画表示加载或完成比例。' },
      { name: '线性进度条（Linear Progress）', desc: '用横向线条表示加载或完成比例。' },
      { name: '占位图（Placeholder）', desc: '图片或内容加载前显示的临时内容。' },
      { name: '空状态（Empty State）', desc: '无内容时显示说明和引导操作。' },
    ],
  },
  {
    page: 'Android · 输入与选择',
    items: [
      { name: '文本输入框（TextField/EditText）', desc: '输入单行或多行文字的基础控件。' },
      { name: '轮廓输入框（Outlined Text Field）', desc: '带完整轮廓边框的 Material 输入框。' },
      { name: '搜索栏（Search Bar）', desc: '用于输入关键词、显示建议和搜索结果。' },
      { name: '复选框（Checkbox）', desc: '独立选择或取消选择多个选项。' },
      { name: '单选按钮（Radio Button）', desc: '从一组互斥选项中选择一个。' },
      { name: '开关（Switch）', desc: '在开启和关闭状态之间切换。' },
      { name: '滑块（Slider）', desc: '在数值范围内拖动选择一个值。' },
      { name: '范围滑块（Range Slider）', desc: '通过两个滑块选择最小值和最大值。' },
      { name: '下拉菜单（Dropdown Menu）', desc: '点击锚点后展开一组选项或命令。' },
      { name: '暴露式下拉菜单（Exposed Dropdown）', desc: '与输入框结合、可直接看到当前值的下拉选择器。' },
      { name: '日期选择器（Date Picker）', desc: '通过日历或输入模式选择日期。' },
      { name: '日期范围选择器（Date Range Picker）', desc: '选择开始和结束日期。' },
      { name: '时间选择器（Time Picker）', desc: '通过时钟或输入模式选择时间。' },
      { name: '数字键盘（Numeric Keyboard）', desc: '为数字、金额或电话输入显示的软键盘。' },
      { name: '密码输入框（Password Field）', desc: '隐藏输入内容并可切换可见性的输入框。' },
      { name: '一次性验证码输入框（OTP Input）', desc: '按位输入短信或身份验证码。' },
      { name: '文件选择器（File Picker）', desc: '从设备存储或文档提供方选择文件。' },
      { name: '照片选择器（Photo Picker）', desc: '从系统照片和视频库选择媒体。' },
    ],
  },
  {
    page: 'Android · 按钮与手势操作',
    items: [
      { name: '填充按钮（Filled Button）', desc: '高强调度的主要 Material 操作按钮。' },
      { name: '色调按钮（Filled Tonal Button）', desc: '强调度低于填充按钮的有底色按钮。' },
      { name: '轮廓按钮（Outlined Button）', desc: '带边框、用于中等强调操作的按钮。' },
      { name: '文字按钮（Text Button）', desc: '用于低强调操作的纯文字按钮。' },
      { name: '图标按钮（Icon Button）', desc: '仅显示图标的紧凑操作按钮。' },
      { name: '悬浮操作按钮（FAB）', desc: '浮于内容上方并突出页面主要操作的按钮。' },
      { name: '扩展悬浮按钮（Extended FAB）', desc: '同时显示图标和文字的悬浮操作按钮。' },
      { name: '长按（Long Press）', desc: '持续按住组件触发次要操作或上下文菜单。' },
      { name: '滑动操作（Swipe Action）', desc: '横向滑动列表项触发删除、归档等操作。' },
      { name: '拖拽排序（Drag and Drop）', desc: '长按拖动条目改变顺序或位置。' },
      { name: '双击（Double Tap）', desc: '连续点击两次触发缩放、点赞等快捷操作。' },
      { name: '双指缩放（Pinch to Zoom）', desc: '通过双指开合缩放图片、地图或内容。' },
    ],
  },
  {
    page: 'Android · 弹窗、反馈与系统界面',
    items: [
      { name: '警告对话框（Alert Dialog）', desc: '展示重要信息并要求确认、取消或选择。' },
      { name: '全屏对话框（Full-screen Dialog）', desc: '占满屏幕处理复杂编辑或选择任务。' },
      { name: '底部弹窗（Bottom Sheet）', desc: '从屏幕底部出现的补充内容或操作面板。' },
      { name: '模态底部弹窗（Modal Bottom Sheet）', desc: '带遮罩并暂时阻断主界面操作的底部面板。' },
      { name: '常驻底部面板（Persistent Bottom Sheet）', desc: '与主内容同时可见、可展开收起的底部面板。' },
      { name: '轻提示（Toast）', desc: '短暂显示、通常不带操作的系统级提示。' },
      { name: '消息条（Snackbar）', desc: '屏幕底部短暂显示反馈并可带一个操作。' },
      { name: '权限请求（Permission Dialog）', desc: '请求相机、定位、通知等运行时权限的系统弹窗。' },
      { name: '系统分享面板（Sharesheet）', desc: '选择应用或联系人分享内容的系统界面。' },
      { name: '通知（Notification）', desc: '出现在通知栏、锁屏或横幅中的应用消息。' },
      { name: '通知渠道（Notification Channel）', desc: 'Android 中用于分类和管理通知行为的设置项。' },
      { name: '前台服务通知（Foreground Service Notification）', desc: '前台服务运行期间持续显示的通知。' },
      { name: '悬浮窗（Overlay/Floating Window）', desc: '覆盖在其他应用上方的小窗或浮动控件。' },
      { name: '应用小部件（App Widget）', desc: '放置在系统桌面上的应用信息和快捷操作组件。' },
      { name: '启动画面（Splash Screen）', desc: '应用冷启动时显示品牌和过渡状态的界面。' },
      { name: '生物识别提示（Biometric Prompt）', desc: '使用指纹或面容完成身份验证的系统弹窗。' },
      { name: '应用内更新（In-app Update）', desc: '在应用内提示并执行版本更新的流程界面。' },
      { name: '离线/重试提示（Offline/Retry State）', desc: '网络不可用或请求失败时提供状态和重试入口。' },
    ],
  },
  {
    page: 'Android · 媒体、地图与设备能力',
    items: [
      { name: '视频播放器（Video Player）', desc: '播放视频并提供进度、暂停、音量和全屏控制。' },
      { name: '音频播放器（Audio Player）', desc: '播放音频并显示进度、封面和播放控制。' },
      { name: '相机预览（Camera Preview）', desc: '实时显示摄像头画面和拍摄控制。' },
      { name: '扫码取景框（Scanner Viewfinder）', desc: '显示二维码或条码识别范围的相机界面。' },
      { name: '地图（Map View）', desc: '显示地图、标记、路线和定位信息。' },
      { name: '地图标记（Map Marker）', desc: '在地图坐标上表示地点或对象。' },
      { name: '网页视图（WebView）', desc: '在 Android 应用内嵌并显示网页内容。' },
      { name: '文档预览（Document Preview）', desc: '在应用内查看 PDF、文档或其他文件。' },
      { name: '下载进度（Download Progress）', desc: '展示文件下载状态、速度和完成比例。' },
      { name: '媒体控制通知（Media Notification）', desc: '在通知栏或锁屏控制音视频播放。' },
    ],
  },
];

let currentToolboxTab = 'ui';
let uiDictionaryQuery = '';

function switchToolboxTab(tab) {
  currentToolboxTab = tab;
  document.getElementById('btn-toolbox-ui')?.classList.toggle('active-tab', tab === 'ui');
  document.getElementById('btn-toolbox-commands')?.classList.toggle('active-tab', tab === 'commands');
  const ui = document.getElementById('toolbox-tab-ui');
  const commands = document.getElementById('toolbox-tab-commands');
  if (ui) ui.style.display = tab === 'ui' ? 'block' : 'none';
  if (commands) commands.style.display = tab === 'commands' ? 'block' : 'none';
  if (tab === 'ui') renderUiDictionary();
}

function filterUiDictionary(value) {
  uiDictionaryQuery = (value || '').trim().toLocaleLowerCase();
  renderUiDictionary();
}

function renderUiDictionary() {
  const container = document.getElementById('ui-dictionary-list');
  if (!container) return;

  const groups = UI_DICTIONARY.map(group => ({
    ...group,
    items: group.items.filter(item => {
      if (!uiDictionaryQuery) return true;
      return `${group.page} ${item.name} ${item.desc || ''}`.toLocaleLowerCase().includes(uiDictionaryQuery);
    }),
  })).filter(group => group.items.length > 0);

  const visibleCount = groups.reduce((total, group) => total + group.items.length, 0);
  const totalCount = UI_DICTIONARY.reduce((total, group) => total + group.items.length, 0);
  const count = document.getElementById('ui-dictionary-count');
  if (count) count.textContent = uiDictionaryQuery ? `找到 ${visibleCount} / ${totalCount} 项` : `共 ${totalCount} 项`;

  if (!groups.length) {
    container.innerHTML = '<div style="padding:28px;text-align:center;color:var(--text-muted);">没有匹配的组件名称，请尝试中文名、英文名或组件用途。</div>';
    return;
  }

  container.innerHTML = groups.map(group => `
    <section style="margin-bottom:18px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
        <h3 style="font-size:15px;margin:0;color:var(--text-primary);">${escapeHtml(group.page)}</h3>
        <span style="font-size:12px;color:var(--text-muted);">${group.items.length} 项</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px;">
        ${group.items.map(item => renderUiDictionaryItem(group.page, item)).join('')}
      </div>
    </section>
  `).join('');
}

function renderUiDictionaryItem(page, item) {
  const encodedPage = encodeURIComponent(page);
  const encodedName = encodeURIComponent(item.name);
  const encodedDesc = encodeURIComponent(item.desc || '');
  return `
    <article style="border:1px solid var(--border-color);border-radius:8px;background:var(--bg-secondary);padding:10px;display:flex;flex-direction:column;gap:8px;">
      <div>
        <div style="font-size:14px;font-weight:600;color:var(--text-primary);">${escapeHtml(item.name)}</div>
        <div style="font-size:12px;color:var(--text-muted);line-height:1.5;margin-top:4px;">${escapeHtml(item.desc || '')}</div>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:auto;">
        <button class="btn btn-sm btn-primary" style="font-size:12px;padding:4px 8px;" onclick="insertUiNameToPrompt('${encodedPage}','${encodedName}','${encodedDesc}')">加入提示词</button>
        <button class="btn btn-sm btn-outline" style="font-size:12px;padding:4px 8px;" onclick="copyUiNameText('${encodedPage}','${encodedName}','${encodedDesc}')">复制说法</button>
        <button class="btn btn-sm btn-outline" style="font-size:12px;padding:4px 8px;" onclick="appendUiNameRequirement('${encodedName}')">写需求</button>
      </div>
    </article>
  `;
}

function decodeUiValue(value) {
  try { return decodeURIComponent(value || ''); } catch (_) { return value || ''; }
}

function insertUiNameToPrompt(pageValue, nameValue, descValue) {
  const page = decodeUiValue(pageValue);
  const name = decodeUiValue(nameValue);
  if (typeof openGlobalPromptPanel === 'function') openGlobalPromptPanel('toolbox');
  const input = document.getElementById('global-prompt-component-input');
  if (input) {
    const phrase = `${page} / ${name}`;
    const parts = input.value.split(',').map(v => v.trim()).filter(Boolean);
    if (!parts.includes(phrase)) parts.push(phrase);
    input.value = parts.join(', ');
  }
  const source = document.getElementById('global-prompt-source');
  if (source) source.textContent = `🧰 来源：开发工具箱 - ${page}`;
  showToast(`已加入：${name}`, 'success');
  if (typeof updateGlobalPromptPreview === 'function') updateGlobalPromptPreview();
}

function copyUiNameText(pageValue, nameValue, descValue) {
  const page = decodeUiValue(pageValue);
  const name = decodeUiValue(nameValue);
  const desc = decodeUiValue(descValue);
  const text = `${page}里的「${name}」${desc ? '：' + desc : ''}`;
  navigator.clipboard?.writeText(text).then(
    () => showToast('已复制界面说法', 'success'),
    () => showToast(text, 'info')
  );
}

function appendUiNameRequirement(nameValue) {
  const name = decodeUiValue(nameValue);
  if (typeof openGlobalPromptPanel === 'function') openGlobalPromptPanel('toolbox');
  const textarea = document.getElementById('global-prompt-user-req');
  if (textarea) {
    const prefix = `请优化「${name}」`;
    textarea.value = textarea.value.trim() ? `${textarea.value.trim()}\n${prefix}` : prefix;
    textarea.focus();
  }
  if (typeof updateGlobalPromptPreview === 'function') updateGlobalPromptPreview();
}
