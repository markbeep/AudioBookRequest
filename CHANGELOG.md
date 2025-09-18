# Changelog

## [1.7.0](https://github.com/markbeep/AudioBookRequest/compare/v1.6.2...v1.7.0) (2025-09-18)


### Features

* Add user extra data field. Closes [#145](https://github.com/markbeep/AudioBookRequest/issues/145) ([47d939a](https://github.com/markbeep/AudioBookRequest/commit/47d939a987015dbfd15109aaa11e9a6ee6b8b5b3))


### Bug Fixes

* correctly handle initial user creation on forced login-type. Closes [#143](https://github.com/markbeep/AudioBookRequest/issues/143) ([f18fb02](https://github.com/markbeep/AudioBookRequest/commit/f18fb02ba9b50f5fb4399bb13549d2ca1be34a59))
* use the device preference for the default light/dark mode. Closes [#148](https://github.com/markbeep/AudioBookRequest/issues/148) ([03ec7b3](https://github.com/markbeep/AudioBookRequest/commit/03ec7b3a8335b749037ae9ad0255399e792b9169))


### Miscellaneous Chores

* add just for easier commands ([56eb319](https://github.com/markbeep/AudioBookRequest/commit/56eb319ac9c7bf12671da54c0f06d3d6f6c2525b))
* add motivation/features to readme ([7892ac8](https://github.com/markbeep/AudioBookRequest/commit/7892ac86b403fb41214a1d07f434ad9844460f65))
* format users.py ([1483f9f](https://github.com/markbeep/AudioBookRequest/commit/1483f9f98d9f2afc8b20ed95d93e88dcf8b36551))

## [1.6.2](https://github.com/markbeep/AudioBookRequest/compare/v1.6.1...v1.6.2) (2025-09-04)


### Bug Fixes

* html duplicating when changing account password ([8d86aa1](https://github.com/markbeep/AudioBookRequest/commit/8d86aa13a166655534838f90243b0a789aac7074))
* incorrectly redirecting from https to http ([9c6a002](https://github.com/markbeep/AudioBookRequest/commit/9c6a00258dd9d583913480afee42cde276f49eed)), closes [#140](https://github.com/markbeep/AudioBookRequest/issues/140)


### Miscellaneous Chores

* fix readme table ([7822f12](https://github.com/markbeep/AudioBookRequest/commit/7822f12b3807df0644e86170326c9a5130d8e6f7))

## [1.6.1](https://github.com/markbeep/AudioBookRequest/compare/v1.6.0...v1.6.1) (2025-08-28)


### Bug Fixes

* ignore missing booleans on REST api/local file indexer configs ([be3b9c5](https://github.com/markbeep/AudioBookRequest/commit/be3b9c54e54ad1cfb59931cac7a10bca0bb8e6c4))


### Code Refactoring

* separate 'enabled' logic of indexers ([5b24705](https://github.com/markbeep/AudioBookRequest/commit/5b24705f96bdb93a0a78149d9a7485c6c2e89096))

## [1.6.0](https://github.com/markbeep/AudioBookRequest/compare/v1.5.3...v1.6.0) (2025-08-22)


### Features

* add API endpoint to update indexers (mam_id). Closes [#122](https://github.com/markbeep/AudioBookRequest/issues/122) ([9b2cda3](https://github.com/markbeep/AudioBookRequest/commit/9b2cda30c01e8d024cc8e66fdef5cf0d46bc153f))
* update indexer configuration using a local file. Closes [#122](https://github.com/markbeep/AudioBookRequest/issues/122) ([c7bd803](https://github.com/markbeep/AudioBookRequest/commit/c7bd80377c9495e5519cd5a7ab4edc84f1b2a436))


### Code Refactoring

* split up settings router file into a file for each page ([c8279f0](https://github.com/markbeep/AudioBookRequest/commit/c8279f084784dd19bf02631eb31de8befab03eba))

## [1.5.3](https://github.com/markbeep/AudioBookRequest/compare/v1.5.2...v1.5.3) (2025-08-18)


### Bug Fixes

* correctly cache admin user when using the 'none' login type to prevent crashing ([990396a](https://github.com/markbeep/AudioBookRequest/commit/990396a519c0e186bb45a1206856f2922f88da2a))
* restore cached search results without crashing. Closes [#130](https://github.com/markbeep/AudioBookRequest/issues/130) ([b032fbc](https://github.com/markbeep/AudioBookRequest/commit/b032fbc92ee66dc31d9f37bc38fd6131fbeab626))


### Dependencies

* update packages ([9acec07](https://github.com/markbeep/AudioBookRequest/commit/9acec077c0995ac0e7c4db84035f091ca216cd93))


### Miscellaneous Chores

* release-please add changelog-sections ([1701143](https://github.com/markbeep/AudioBookRequest/commit/1701143bb304a20518dfab94c9b7cfbe7e779d9c))


### Code Refactoring

* use class-based authentication to automatically get generated in the OpenAPI specs ([8d08c89](https://github.com/markbeep/AudioBookRequest/commit/8d08c891c4be04919eae25e60b87ed5d250eedd8))

## [1.5.2](https://github.com/markbeep/AudioBookRequest/compare/v1.5.1...v1.5.2) (2025-08-16)


### Features

* add changelog modal when clicking version in the settings ([d07765f](https://github.com/markbeep/AudioBookRequest/commit/d07765f9241b5965914bcc4bbb34abe993c5d733))


### Bug Fixes

* hide wrong book requests and clear cache ([12d323b](https://github.com/markbeep/AudioBookRequest/commit/12d323b9faa9026e3343bdb4d66b31bdee8f96b0))

## [1.5.1](https://github.com/markbeep/AudioBookRequest/compare/v1.5.0...v1.5.1) (2025-08-16)


### Features

* add counters to wishlist pages ([1e93f72](https://github.com/markbeep/AudioBookRequest/commit/1e93f725af86caeefd9b7d44711bb06fb09f247d))
* allow editing of manual requests. Closes [#73](https://github.com/markbeep/AudioBookRequest/issues/73) ([7c549be](https://github.com/markbeep/AudioBookRequest/commit/7c549be1efcb219fe652d4c79f733c597ed297e5))


### Bug Fixes

* correctly always show all books on requests page as admin ([1e93f72](https://github.com/markbeep/AudioBookRequest/commit/1e93f725af86caeefd9b7d44711bb06fb09f247d))


### Miscellaneous Chores

* remove leading v from version number ([5de5cbf](https://github.com/markbeep/AudioBookRequest/commit/5de5cbfcd61c5f52f9fccb38190a42c26fc024a0))

## [1.5.0](https://github.com/markbeep/AudioBookRequest/compare/1.4.9...v1.5.0) (2025-08-16)

### Features

- add API: Users and Status/Health Endpoints ([#117](https://github.com/markbeep/AudioBookRequest/issues/117)) ([7d3e4fe](https://github.com/markbeep/AudioBookRequest/commit/7d3e4fedc672226afb858088e0d6fc5b7ec7604a))
- add more replacement options for download notifications ([3296af4](https://github.com/markbeep/AudioBookRequest/commit/3296af497032c5fa8e2c89b21770e7f259448011))
- add user api ([92a4018](https://github.com/markbeep/AudioBookRequest/commit/92a401879bb71439c8e0ada579c16799059f8748))
- add env variables for forcing login type and initializing username/password ([93a6315](https://github.com/markbeep/AudioBookRequest/commit/93a6315e304a829506136e90fde2f98af71625f9))

### Bug Fixes

- correct api key popup colors and cleanup unused code ([3e21d74](https://github.com/markbeep/AudioBookRequest/commit/3e21d7476df097f2410c3a0af3804ac499df47a6))
- oidc config not outputting errors on invalid endpoint url ([5a8f24c](https://github.com/markbeep/AudioBookRequest/commit/5a8f24cec07e59d39f1208e001c18c1b2f0b68a7))
- wrong color scheme in login/init pages ([5a8f24c](https://github.com/markbeep/AudioBookRequest/commit/5a8f24cec07e59d39f1208e001c18c1b2f0b68a7))
