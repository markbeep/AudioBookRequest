# Changelog

## [Unreleased]

### Bug Fixes

* avoid startup crashes when required config values are missing
* guard Prowlarr/ABS lookups with explicit validation instead of asserts
* default qBittorrent port when unset to prevent invalid base URLs
* add timeouts and directory creation for debug JS fetch
* harden JS string escaping and handle missing changelog file
* reduce duplicate Prowlarr queries by serializing per-ASIN lookups

## [1.9.0](https://github.com/markbeep/AudioBookRequest/compare/v1.8.0...v1.9.0) (2026-01-24)


### Features

* add book recommendations on home page. Closes [#109](https://github.com/markbeep/AudioBookRequest/issues/109) ([e971dd3](https://github.com/markbeep/AudioBookRequest/commit/e971dd321af13c844e4e01d46617780608ca05ba))
* add loose Audiobookshelf integration. Closes [#103](https://github.com/markbeep/AudioBookRequest/issues/103) ([c4f6b8c](https://github.com/markbeep/AudioBookRequest/commit/c4f6b8c02eea9dc903b173ec200afc038bc5822d))
* all website operations can now be handled using the REST API (Closes [#135](https://github.com/markbeep/AudioBookRequest/issues/135)) ([#176](https://github.com/markbeep/AudioBookRequest/issues/176)) ([0dff1f3](https://github.com/markbeep/AudioBookRequest/commit/0dff1f38c8adc8b9f0942ec1ce85d9a05b7d7888))
* allow non-admins to delete their requests. Closes [#171](https://github.com/markbeep/AudioBookRequest/issues/171) ([096d04e](https://github.com/markbeep/AudioBookRequest/commit/096d04e33d055a5bc0c28b4f4b41c5a783b53b40))


### Bug Fixes

* fix missing fetch for js files in dockerfile ([5b985d2](https://github.com/markbeep/AudioBookRequest/commit/5b985d2eaf1db075d3c2f55016907bfc6d91ca08))
* fix search breaking completely when a cached result has been deleted. Closes [#141](https://github.com/markbeep/AudioBookRequest/issues/141) ([096d04e](https://github.com/markbeep/AudioBookRequest/commit/096d04e33d055a5bc0c28b4f4b41c5a783b53b40))
* make inputs on download settings page editable ([0dff1f3](https://github.com/markbeep/AudioBookRequest/commit/0dff1f38c8adc8b9f0942ec1ce85d9a05b7d7888))
* show prowlarr responses in the log when the response is invalid JSON ([096d04e](https://github.com/markbeep/AudioBookRequest/commit/096d04e33d055a5bc0c28b4f4b41c5a783b53b40))


### Performance Improvements

* minimize HTML while templating ([63c9d14](https://github.com/markbeep/AudioBookRequest/commit/63c9d147b56867b1444ab2f8f2f33fbfe5e4fe62))


### Dependencies

* update all dependencies ([6727dc6](https://github.com/markbeep/AudioBookRequest/commit/6727dc67ba643e84de5cbc6e6b5259872e3cf9ed))


### Miscellaneous Chores

* add daisyui install to justfile for local development ([6727dc6](https://github.com/markbeep/AudioBookRequest/commit/6727dc67ba643e84de5cbc6e6b5259872e3cf9ed))
* add tools section to readme ([9140ba8](https://github.com/markbeep/AudioBookRequest/commit/9140ba8e0c8b8a3b034354f328e0d1ec9690304d))
* fix uv python version ([6bfba44](https://github.com/markbeep/AudioBookRequest/commit/6bfba44536de66a80000f5ce334440101f522194))
* send along User-Agent in headers on API calls ([d3a9f34](https://github.com/markbeep/AudioBookRequest/commit/d3a9f3411aaa923e570a6bbd629fa05e2d4df923))
* switch to GPLv3 license ([2300d25](https://github.com/markbeep/AudioBookRequest/commit/2300d25347f5b82218c1f26600122f4aa0009d6c))


### Code Refactoring

* replace "older" `Optional` tyings with `|None` ([6727dc6](https://github.com/markbeep/AudioBookRequest/commit/6727dc67ba643e84de5cbc6e6b5259872e3cf9ed))
* rework how audiobooks are cached and how requests are handled ([#175](https://github.com/markbeep/AudioBookRequest/issues/175)) ([096d04e](https://github.com/markbeep/AudioBookRequest/commit/096d04e33d055a5bc0c28b4f4b41c5a783b53b40))


### Tests

* change type checker to strict basedpyright and fix up typing issues ([096d04e](https://github.com/markbeep/AudioBookRequest/commit/096d04e33d055a5bc0c28b4f4b41c5a783b53b40))
* switch from pyright to pyrefly for typing ([63c9d14](https://github.com/markbeep/AudioBookRequest/commit/63c9d147b56867b1444ab2f8f2f33fbfe5e4fe62))


### Build System

* split up and minimize Dockerfile and image size ([#172](https://github.com/markbeep/AudioBookRequest/issues/172)) ([23aaf16](https://github.com/markbeep/AudioBookRequest/commit/23aaf169d703f9b6469c2e6e3b55abead1b6b9f1))

## [1.8.0](https://github.com/markbeep/AudioBookRequest/compare/v1.7.0...v1.8.0) (2025-10-04)


### Features

* add postgresql support ([abd75a9](https://github.com/markbeep/AudioBookRequest/commit/abd75a96dad8f7e96a0c564f3bf7625cdf5ee831))


### Bug Fixes

* correctly handle book metadata server being down ([399d82e](https://github.com/markbeep/AudioBookRequest/commit/399d82ed4e9d79ab968312067d258239863e0052))
* get infohash from magnet link ([6ac754e](https://github.com/markbeep/AudioBookRequest/commit/6ac754e2621fcbb31a6bbd32a270a1da7fafa30c))


### Miscellaneous Chores

* fix devcontainer ([05f505d](https://github.com/markbeep/AudioBookRequest/commit/05f505ddb30435b53bd7f6d64703ceaad2dd2271))
* install psycopg binary instead of non ([82f356f](https://github.com/markbeep/AudioBookRequest/commit/82f356f0cf0afbeb9e70e2ce49ac500d1fd6d554))

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
