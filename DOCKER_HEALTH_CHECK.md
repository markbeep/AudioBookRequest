# Docker Health Check Documentation

## Overview

AudioBookRequest now includes a comprehensive Docker health check system that monitors the application's health and availability. This feature is essential for production deployments, container orchestration, and monitoring systems.

## Health Check Endpoint

The health check uses the `/api/v1/health` endpoint which:
- **No authentication required**
- **Fast response time** (typically <50ms)
- **Minimal resource usage**
- **Returns JSON with status and uptime information**

### Example Response

```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "uptime": 3600.5
}
```

## Docker Configuration

### Dockerfile Health Check

The health check is built into the Docker image:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:$ABR_APP__PORT/api/v1/health || exit 1
```

**Parameters:**
- `--interval=30s`: Check every 30 seconds
- `--timeout=10s`: Fail if check takes longer than 10 seconds
- `--start-period=5s`: Allow 5 seconds for the app to start before first check
- `--retries=3`: Mark as unhealthy after 3 consecutive failures

### Docker Compose Health Check

The docker-compose.yml includes health check configuration:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 5s
```

## Health Check States

Docker tracks three health states:

1. **starting**: During the start period or initial checks
2. **healthy**: Health checks are passing
3. **unhealthy**: Health checks are failing

## Monitoring Integration

### Docker Commands

```bash
# Check container health status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# View detailed health check logs
docker inspect --format='{{json .State.Health}}' <container_name>

# Get health check history
docker inspect <container_name> | jq '.[] | .State.Health.Log'
```

### Docker Compose

```bash
# Check service health
docker-compose ps

# View health check logs
docker-compose logs web
```

### Container Orchestration

#### Kubernetes

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: audiobookrequest
    image: markbeep/audiobookrequest:latest
    livenessProbe:
      httpGet:
        path: /api/v1/health
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 30
      timeoutSeconds: 10
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /api/v1/health
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 10
      timeoutSeconds: 5
      failureThreshold: 3
```

#### Docker Swarm

```yaml
version: '3.8'
services:
  audiobookrequest:
    image: markbeep/audiobookrequest:latest
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s
    deploy:
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
```

## Load Balancer Integration

### HAProxy

```haproxy
backend audiobookrequest
    balance roundrobin
    option httpchk GET /api/v1/health
    server app1 audiobookrequest:8000 check
    server app2 audiobookrequest:8000 check
```

### Nginx (with upstream health checks)

```nginx
upstream audiobookrequest {
    server audiobookrequest:8000;
    keepalive 32;
}

server {
    location /health {
        access_log off;
        proxy_pass http://audiobookrequest/api/v1/health;
    }
}
```

### Traefik

```yaml
version: '3.8'
services:
  audiobookrequest:
    image: markbeep/audiobookrequest:latest
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.audiobookrequest.rule=Host(`audiobookrequest.example.com`)"
      - "traefik.http.services.audiobookrequest.loadbalancer.healthcheck.path=/api/v1/health"
      - "traefik.http.services.audiobookrequest.loadbalancer.healthcheck.interval=30s"
```

## Monitoring Systems

### Prometheus

```yaml
# prometheus.yml
- job_name: 'audiobookrequest-health'
  static_configs:
    - targets: ['audiobookrequest:8000']
  metrics_path: /api/v1/health
  scrape_interval: 30s
```

### Grafana Dashboard

Create alerts based on health check metrics:
- Container restart count
- Health check failure rate
- Response time trends

## Testing

Test the health check system:

```bash
# Run the test script
python test_health_check.py

# Manual test
curl -f http://localhost:8000/api/v1/health

# Test Docker health check
docker run --rm markbeep/audiobookrequest:latest curl -f http://localhost:8000/api/v1/health
```

## Troubleshooting

### Common Issues

1. **Health check failing but app works**
   - Check if the health endpoint is accessible
   - Verify port configuration
   - Check firewall rules

2. **Health check timing out**
   - Increase timeout value
   - Check application startup time
   - Verify database connectivity

3. **Container marked as unhealthy**
   - Check application logs
   - Verify health endpoint response
   - Check resource constraints

### Debug Commands

```bash
# Check health endpoint directly
curl -v http://localhost:8000/api/v1/health

# View Docker health check logs
docker logs <container_name>

# Inspect health check configuration
docker inspect <container_name> | grep -A 10 -B 10 Health
```

## Security Considerations

- The health endpoint is **public** (no authentication required)
- Only returns basic status information
- No sensitive data exposed
- Suitable for external monitoring systems

## Performance Impact

- **Minimal CPU usage**: Simple JSON response
- **Low memory footprint**: No database queries
- **Fast response**: Typically <50ms
- **No side effects**: Read-only operation

## Benefits

✅ **Automated monitoring**: Detect failures quickly  
✅ **Zero-downtime deployments**: Ensure new containers are healthy  
✅ **Load balancer integration**: Remove unhealthy instances  
✅ **Container orchestration**: Automatic restart of failed containers  
✅ **Alerting**: Integration with monitoring systems  
✅ **Debugging**: Clear indication of application status  

This health check system ensures AudioBookRequest runs reliably in production environments with proper monitoring and automated failure recovery.