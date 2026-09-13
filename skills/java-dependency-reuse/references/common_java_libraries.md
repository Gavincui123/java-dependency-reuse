# Java 依赖现成功能速查表

写 Java 工具方法前，先对照本表。**命中即用依赖 API，不要手写**。
本表按"想实现的功能"组织；是否真的可用，以 `view_class_api.py` 查到的真实签名为准。

## 0. 判定流程

1. 想实现一个功能/工具方法 → 在本表找对应场景
2. `search_class_in_jars.py --class <类名> --pom <pom>` 确认类在依赖中
3. `view_class_api.py --class <完整类名> --pom <pom>` 核对真实方法签名
4. 命中 → 直接调用，注释标注来源；未命中 → 才手写

## 1. 字符串处理

| 想实现 | 别手写，用 | 典型 API |
|---|---|---|
| 判空/空白 | Commons Lang3 `StringUtils` | `isBlank/isNotBlank/isEmpty` |
| 判空/空白 | Hutool `StrUtil` | `isBlank/isNotBlank` |
| 判空 | Spring `StringUtils` | `hasText/hasLength` |
| join/split | Guava `Joiner` / `Splitter` | `Joiner.on(",").join(list)`、`Splitter.on(',').trimResults()` |
| join/split | Commons Lang3 `StringUtils` | `join(array, sep)`、`split(str, sep)` |
| 截断/省略 | Commons Lang3 `StringUtils` | `abbreviate(str, maxWidth)` |
| 首字母大小写 | Commons Lang3 `StringUtils` | `capitalize/uncapitalize` |
| 驼峰/下划线互转 | Hutool `StrUtil` | `toCamelCase/toUnderlineCase` |
| 空白字符清理 | Guava `CharMatcher` | `CharMatcher.whitespace().trimFrom(s)` |
| 正则匹配/提取 | JDK `Pattern`/`Matcher`（无需依赖） | `Pattern.compile` |
| 移除/替换 | Commons Lang3 `StringUtils` | `remove/removeStart/removeEnd/replace` |
| 子串安全截取 | Commons Lang3 `StringUtils` | `substring/substringBefore/substringAfter` |
| 左/右补全 | Commons Lang3 `StringUtils` | `leftPad/rightPad` |
| 判断包含忽略大小写 | Commons Lang3 `StringUtils` | `containsIgnoreCase` |

## 2. 集合操作

| 想实现 | 别手写，用 | 典型 API |
|---|---|---|
| 集合判空 | Commons Collections4 `CollectionUtils` | `isEmpty/isNotEmpty` |
| 集合判空 | Hutool `CollUtil` | `isEmpty/isNotEmpty` |
| 快速构造 list/map/set | Guava `Lists`/`Maps`/`Sets` | `Lists.newArrayList(...)`、`Maps.newHashMap()` |
| 不可变集合 | Guava `ImmutableList`/`ImmutableMap` | `ImmutableList.of(...)` |
| 过滤/转换 | JDK `Stream`（无需依赖） | `filter/map/collect` |
| 分组 | JDK `Collectors.groupingBy` | `groupingBy(Function)` |
| 合并/交集/差集 | Commons Collections4 `CollectionUtils` | `union/intersection/subtract` |
| 合并/交集/差集 | Hutool `CollUtil` | `union/intersection/disjunction` |
| 取交集/差集 | Guava `Sets` | `intersection/difference/union` |
| 安全取值（避免越界） | Commons Lang3 `ArrayUtils` | `get(arr, index, defaultValue)` |
| 数组判空 | Commons Lang3 `ArrayUtils` | `isEmpty/isNotEmpty` |
| 批量分页切分 | Guava `Lists` | `Lists.partition(list, size)` |
| 批量分页切分 | Hutool `CollUtil` | `split(list, size)` |
| 去重保持顺序 | JDK `LinkedHashSet`（无需依赖） | 或用 Stream `distinct()` |
| Map 默认值 | Guava `Maps` / JDK `Map.getOrDefault` | `getOrDefault` |
| 多值 Map | Guava `Multimap` | `ArrayListMultimap.create()` |
| 循环引用安全 toString | Commons Lang3 `ToStringBuilder` | `reflectionToString` |
| 集合为空返回默认 | Hutool `CollUtil` | `emptyIfNull(list)` |

## 3. 判空与对象

| 想实现 | 别手写，用 | 典型 API |
|---|---|---|
| 对象判空/判非空 | JDK `Objects`（无需依赖） | `isNull/nonNull/requireNonNull` |
| 对象判空 | Commons Lang3 `ObjectUtils` | `isEmpty/isNotEmpty` |
| 对象判空 | Hutool `ObjectUtil` | `isEmpty/isNotEmpty` |
| 条件断言（参数校验） | Spring `Assert` | `notNull/hasText/isTrue/notEmpty` |
| 条件断言 | Guava `Preconditions` | `checkArgument/checkNotNull/checkState` |
| 条件断言 | Hutool `Assert` | `notNull/isTrue/notEmpty` |
| 比较对象 | Commons Lang3 `ObjectUtils` | `compare/equals` |
| 取第一个非空 | Commons Lang3 `ObjectUtils` | `firstNonNull` |
| 取第一个非空 | Guava `MoreObjects` | `firstNonNull` |

## 4. Bean 复制 / 转换

| 想实现 | 别手写，用 | 典型 API |
|---|---|---|
| 同名属性拷贝 | Spring `BeanUtils` | `copyProperties(source, target)` |
| 同名属性拷贝 | Hutool `BeanUtil` | `copyProperties(source, target)` |
| 深拷贝 | Hutool `BeanUtil` | `cloneBean`（需实现 Serializable） |
| 类型转换 | Hutool `Convert` | `toStr/toInt/toLong/toDate` |
| Bean ↔ Map | Hutool `BeanUtil` | `beanToMap/mapToBean` |
| JSON ↔ 对象 | Jackson（见第 9 节） | `ObjectMapper.readValue/writeValueAsString` |

## 5. 日期时间

| 想实现 | 别手写，用 | 典型 API |
|---|---|---|
| 新日期/格式化 | JDK `java.time`（无需依赖） | `LocalDate/LocalDateTime/DateTimeFormatter` |
| 日期格式化/解析 | Hutool `DateUtil` | `parse/format`、`LocalDateTimeUtil` |
| 计算差值/加减 | JDK `java.time` | `plusDays/minusDays/Period/Duration` |
| 时间戳 ↔ 日期 | Hutool `DateUtil` | `of(timestamp)` |
| 当月/季度/年龄等 | Hutool `DateUtil` | `beginOfMonth/age` |
| 带时区处理 | JDK `ZonedDateTime/ZoneId` | 无需依赖 |

## 6. IO / 文件

| 想实现 | 别手写，用 | 典型 API |
|---|---|---|
| 读文件为字符串 | Commons IO `FileUtils` | `readFileToString` |
| 写字符串到文件 | Commons IO `FileUtils` | `writeStringToFile` |
| 复制流/文件 | Commons IO `IOUtils`/`FileUtils` | `copy/copyFile` |
| 删除目录递归 | Commons IO `FileUtils` | `deleteDirectory` |
| 文件读为字节/行 | Hutool `FileUtil` | `readBytes/readLines/readUtf8String` |
| 写文件 | Hutool `FileUtil` | `writeUtf8String` |
| 流复制 | Hutool `IoUtil` | `copy` |
| 资源读取（classpath） | Spring `Resource`/`ClassPathResource` | `getInputStream` |
| 流关闭/读行 | Hutool `IoUtil` | `close/readLines` |

## 7. 加密 / 摘要 / 编码

| 想实现 | 别手写，用 | 典型 API |
|---|---|---|
| MD5/SHA 摘要 | Commons Codec `DigestUtils` | `md5Hex/sha256Hex` |
| MD5/SHA 摘要 | Hutool `SecureUtil` | `md5/sha256` |
| Base64 编解码 | JDK `Base64`（无需依赖） | `getEncoder/getDecoder` |
| URL 编解码 | JDK `URLEncoder/URLDecoder` | 无需依赖 |
| AES/RSA 加解密 | Hutool `SecureUtil` | `aes/rsa` |
| 随机数/验证码 | Commons Lang3 `RandomStringUtils` | `randomNumeric/randomAlphanumeric` |
| 随机数/验证码 | Hutool `RandomUtil` | `randomNumbers/randomString` |
| 唯一 ID | Hutool `IdUtil` | `fastSimpleUUID/fastUUID/snowflake` |
| 唯一 ID | JDK `UUID`（无需依赖） | `UUID.randomUUID()` |

## 8. HTTP / 网络

| 想实现 | 别手写，用 | 典型 API |
|---|---|---|
| 简单 GET/POST | Spring `RestTemplate`/`WebClient` | `getForObject/postForObject` |
| 简单 GET/POST | Hutool `HttpUtil` | `get/post` |
| 高级 HTTP 客户端 | Apache HttpClient5 / OkHttp | 按项目现有依赖 |
| URL 拼接/解析 | Hutool `UrlBuilder` / JDK `URI` | 无需额外依赖优先用 JDK |

## 9. JSON

| 想实现 | 别手写，用 | 典型 API |
|---|---|---|
| 序列化/反序列化 | Jackson `ObjectMapper` | `writeValueAsString/readValue` |
| 序列化/反序列化 | Hutool `JSONUtil` | `toJsonStr/toBean` |
| 序列化/反序列化 | Gson `Gson` / Fastjson2 | 按项目现有依赖 |
| 树形解析 | Jackson `JsonNode` | `readTree` |

## 10. 其他高频场景

| 想实现 | 别手写，用 | 典型 API |
|---|---|---|
| 日志 | SLF4J `LoggerFactory` | `getLogger(Class)`，勿用 System.out |
| 断言/参数校验 | 见第 3 节 | Spring `Assert` / Guava `Preconditions` |
| 函数式 Optional | JDK `Optional`（无需依赖） | `ofNullable/map/orElseThrow` |
| 优雅关闭资源 | JDK try-with-resources（无需依赖） | 无需依赖 |
| 分页参数/PageResult | Spring Data `Pageable` | 或按项目封装 |
| 排序 | JDK `Comparator`/`Collections.sort` | 无需依赖 |
| 类型安全转换 | Hutool `Convert` | `convert(Class, obj)` |
| 原子/并发工具 | JDK `java.util.concurrent`（无需依赖） | `AtomicLong/CompletableFuture` |
| 布隆过滤器/缓存 | Guava `BloomFilter`/`CacheBuilder` | 按项目场景 |

## 11. 需要警惕的"自己实现陷阱"

- **手写加密/哈希** → 用 Commons Codec / Hutool / JDK
- **手写日期格式化线程安全问题** → 用 `java.time`（不可变）或 Hutool
- **手写 Bean 拷贝反射** → 用 Spring/Hutool BeanUtils
- **手写 JSON 拼接** → 用 Jackson（项目标配）
- **手写 Base64/URL 编码** → JDK 自带，别造
- **手写集合转字符串拼接** → `String.join` / Guava Joiner / Commons StringUtils.join

## 12. 常见依赖 → 能力速查

| 依赖坐标 | 核心能力 |
|---|---|
| `org.apache.commons:commons-lang3` | 字符串/数组/对象/数学/异常工具 |
| `org.apache.commons:commons-collections4` | 集合工具、多值 Map、Bag |
| `org.apache.commons:commons-io` | 文件/流工具 |
| `commons-codec:commons-codec` | 摘要、Base64、编解码 |
| `com.google.guava:guava` | 集合/字符串/缓存/并发/前置条件 |
| `cn.hutool:hutool-all` | 一站式工具：字符串/集合/日期/文件/加密/JSON/HTTP |
| `org.springframework:spring-core` | `StringUtils`/`ObjectUtils`/`Assert`/`BeanUtils`/`Resource` |
| `org.springframework:spring-web` | `RestTemplate`、URI 工具 |
| `com.fasterxml.jackson.core:jackson-databind` | JSON 序列化 |
| `org.projectlombok:lombok` | `@Data/@Builder/@Slf4j` 减少样板代码 |
