## Discrepancies Found

I've identified **7 significant inconsistencies** that would cause runtime failures:

### 1. **Database Password** (Critical)
- **docker-compose.yml**: `POSTGRES_PASSWORD: secret`
- **All others** (.env.example, config/default.json, README): `postgres`
- **Impact**: App cannot connect to database in Docker environment

### 2. **Redis Host/URL** (Critical)
- **docker-compose.yml**: `redis://:redispass123@redis:6379` (uses service name `redis`)
- **config/default.json**: `redis://cache:6379` (uses hostname `cache`)
- **.env.example**: `REDIS_HOST=localhost` (uses `localhost`)
- **Impact**: App may fail to connect to Redis depending on which config is used

### 3. **Node Environment**
- **docker-compose.yml**: `NODE_ENV: production`
- **.env.example**: `NODE_ENV: development`
- **Impact**: Security & behavior differ between expected and actual environment

### 4. **Session Secret**
- **docker-compose.yml**: `${SESSION_SECRET}` (requires external env var, will be empty if not set)
- **.env.example**: `change-me-in-production` (placeholder)
- **config/default.json**: `default-session-secret` (hardcoded default)
- **Impact**: Session handling inconsistent; docker-compose may have no secret at all

### 5. **Logging Level**
- **.env.example**: `LOG_LEVEL: debug`
- **config/default.json**: `logging.level: info`
- **Impact**: Different verbosity in logs

### 6. **Port Mapping**
- **docker-compose.yml**: `8080:3000` (app accessible on **8080**, not 3000)
- **README & .env.example**: Say to visit `localhost:3000`
- **Impact**: Users follow README and hit wrong port

### 7. **Redis Password in config/default.json**
- **Issue**: Hardcodes `"password": "redispass123"` separately from URL
- **Problem**: Unclear if password is in the URL string or should be used separately; ignores REDIS_PASSWORD from environment

## Recommendations

1. **Fix docker-compose.yml**: Change `secret` → `postgres` for POSTGRES_PASSWORD
2. **Standardize Redis host**: Use `redis` (service name) in config/default.json, or use environment variable
3. **Align NODE_ENV**: Set to `production` in docker-compose, `development` in .env.example
4. **Fix Session Secret**: Don't leave it empty in docker-compose; either set a default or require it
5. **Update README**: Say to visit `localhost:8080` (or change docker-compose port mapping to `3000:3000`)
6. **Consistent logging**: Choose one level across all configs

Would you like me to fix these inconsistencies?