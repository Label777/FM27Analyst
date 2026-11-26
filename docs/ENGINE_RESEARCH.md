# Разведка движка FM27 (загрузка всей базы, как Genie Scout)

Дата: 26.11.2026, FM27 Demo 27.1.1.2511875. Инструмент: «Разведка движка» в плагине FM27 Analyst Bridge 0.2.1
(`Explorer.cs`): обходит справочник `SI.Bindable.Reference.Core.ReferenceIdentifierSet` / `PropertyIdentifierSet`.
Полный справочник — `BepInEx/plugins/FM27AnalystBridge/engine-registry.txt` на компьютере пользователя
(в публичный репозиторий не кладём: это идентификаторы из игры).

## Что нашли

- Типов данных: 1038, свойств: 16258. Справочник читается без ошибок.
- Вызов `ReferenceIDInfo.GetInstance()` у типа без экземпляра → AccessViolation (игра закрывается):
  перед любым вызовом нативной функции проверять указатель (`GetInstanceFunc`, `GetPropertiesFunc`, …).
- Игрок — тип `person` (1300+ свойств): все атрибуты (`AttributeFinishing` … `AttributeWorkRate`, в т.ч.
  характер: `AttributeAmbition`, `AttributeLoyalty`, `AttributePressure`, `AttributeProfessionalism`, `AttributeControversy`,
  `AttributeSportsmanship`, `AttributeTemperament`, `AttributeAdaptability`), владение позициями (`AbilityCentreBack` … SByte),
  `Age`, `CurrentAbilityStarRange`/`starrange`, статистика, лучшие роль/позиция, контракт (`contract`), клуб (`club`).
- Атрибут — тип `attributevalue`: `AttributeMinValue`/`AttributeMaxValue` → движок отдаёт интерфейсу **знание клуба**
  (диапазон по скаутингу), а не истинное значение. Звёзды — `starrange` с `IsScoutsOpinion`.
- Истинных CA/PA игрока в этом слое нет; есть отладочные `DebugCalculatedPerceivedPotential`, `DebugStaffOpinionOfCA/PA`,
  а для персонала — `NonPlayerCurrentAbility` / `NonPlayerPotentialAbility`.
- Поиск: `SearchResult` (Name, DatabaseRecordType, LinkedRecord), `PersonFilter`, `FilterAttribute` — движок умеет искать
  по всей базе; интерфейс получает результаты через каналы `FM.GamePlugin.GameInteropSubsystem` (OpenChannel/AddNode/SetTarget).

## Вывод

1. Через слой интерфейса (каналы движка) можно читать **всю базу в объёме знаний клуба**: все игроки мира с атрибутами-диапазонами,
   звёздами, контрактами, статистикой — без прокрутки таблиц. Это стабильнее чтения памяти: имена свойств, а не адреса.
2. Скрытые истинные значения (CA/PA, точные атрибуты нескаутированных) этим путём не приходят. Как у Genie — только чтение
   нативной памяти движка по смещениям; отдельное исследование, ломается с патчами.

## Следующий шаг

Научиться читать значения свойств одного `person` через `GameInteropSubsystem` (канал → узел → цель → данные),
затем перечислить всех людей через поиск движка и выгрузить базу в ядро.
