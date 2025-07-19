---
title: 'Environment Variables'
description: >
  List of the environment variables that can be set.
date: 2025-06-09T13:46:33+02:00
---

| ENV                        | Description                                                                                                                                                                               | Default   |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| `ABR_APP__PORT`            | The port to run the server on.                                                                                                                                                            | 8000      |
| `ABR_APP__DEBUG`           | If to enable debug mode. Not recommended for production.                                                                                                                                  | false     |
| `ABR_APP__OPENAPI_ENABLED` | If set to `true`, enables an OpenAPI specs page on `/docs`.                                                                                                                               | false     |
| `ABR_APP__CONFIG_DIR`      | The directory path where persistant data and configuration is stored. If ran using Docker or Kubernetes, this is the location a volume should be mounted to.                              | /config   |
| `ABR_APP__LOG_LEVEL`       | One of `DEBUG`, `INFO`, `WARN`, `ERROR`.                                                                                                                                                  | INFO      |
| `ABR_APP__BASE_URL`        | Defines the base url the website is hosted at. If the website is accessed at `example.org/abr/`, set the base URL to `/abr/`                                                              |           |
| `ABR_DB__SQLITE_PATH`      | If relative, path and name of the sqlite database in relation to `ABR_APP__CONFIG_DIR`. If absolute (path starts with `/`), the config dir is ignored and only the absolute path is used. | db.sqlite |
| `ABR_APP__DEFAULT_REGION`  | Default audible region to use for the search. Has to be one of `us, ca, uk, au, fr, de, jp, it, in, es, br`.                                                                              | us        |

{{< alert title="Note" >}} There are two underscores (`__`) between the first
and second part of each environment variable like between `ABR_APP` and `PORT`.
{{< /alert >}}
