# Authentication and Logging Fixes

## Issues Fixed

### 1. Authentication Bug in Recipe List Endpoint

**Problem**: The `/recipe/list` endpoint was returning a 200 status code with an authentication status object when authentication failed, instead of properly rejecting the request with a 403 status.

**Root Cause**: The endpoint was returning the `auth_status` object directly instead of raising an `HTTPException` when authentication failed.

**Fix**: 
- Modified all protected endpoints to raise `HTTPException` with 403 status when authentication fails
- Only the `/auth/validate` endpoint should return the auth status object
- Added detailed logging for authentication attempts

### 2. Insufficient Logging in Docker Environment

**Problem**: Debug logs were not visible when deploying via docker-compose, despite setting up uvicorn logging.

**Root Cause**: No proper logging configuration was in place, and the application was using `uvicorn.error` logger which wasn't properly configured.

**Fix**:
- Created a centralized logging configuration (`sous_chef_kitchen/kitchen/logging_config.py`)
- Configured logging to output to stdout with proper formatting
- Added environment variable `LOG_LEVEL` support (defaults to INFO, set to DEBUG in docker-compose)
- Updated all loggers to use consistent naming (`sous_chef_kitchen.api`, `sous_chef_kitchen.chef`)

## Changes Made

### Files Modified

1. **`sous_chef_kitchen/kitchen/api.py`**
   - Fixed authentication flow in all endpoints
   - Added proper HTTPException handling
   - Improved logging throughout
   - Updated return types to remove `SousChefKitchenAuthStatus` from protected endpoints

2. **`sous_chef_kitchen/kitchen/chef.py`**
   - Added detailed logging to `validate_auth` function
   - Fixed bug in `recipe_list` function
   - Improved error handling

3. **`sous_chef_kitchen/kitchen/logging_config.py`** (new)
   - Centralized logging configuration
   - Environment variable support for log levels
   - Proper stdout output configuration

4. **`docker/docker-compose.yaml`**
   - Added `LOG_LEVEL: DEBUG` environment variable

### Files Created

1. **`test_auth.py`** - Simple test script to verify authentication fixes
2. **`AUTH_FIXES.md`** - This documentation file

## Testing the Fixes

### 1. Test Authentication

Run the test script to verify authentication is working:

```bash
python test_auth.py
```

Expected behavior:
- Requests without authentication should return 403
- Requests with invalid authentication should return 403
- The `/auth/validate` endpoint should return auth status object

### 2. Test Logging

Deploy the application using docker-compose and check the logs:

```bash
cd docker
docker-compose up kitchen-api
```

You should now see detailed logs including:
- Authentication attempts and results
- Recipe list requests
- MediaCloud API calls
- Error details with stack traces

### 3. Test Recipe List Endpoint

With valid authentication:
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "mediacloud-email: YOUR_EMAIL" \
     http://localhost:8000/recipe/list
```

Should return the recipe list with 200 status.

Without authentication:
```bash
curl http://localhost:8000/recipe/list
```

Should return 403 Forbidden.

## Environment Variables

- `LOG_LEVEL`: Set logging level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.
- Set to DEBUG in docker-compose for development

## Notes

- The `/auth/validate` endpoint is the only endpoint that should return the auth status object
- All other protected endpoints now properly raise HTTPException on authentication failure
- Logging is now properly configured for Docker environments
- Detailed authentication logging helps with debugging auth issues 