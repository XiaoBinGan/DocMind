$baseUrl = "http://127.0.0.1:8000"

# Step 1: Create API definition
Write-Host "=== Step 1: 创建 API 定义 ===" -ForegroundColor Cyan
$apiJson = @{
    name = "测试API"
    description = "这是一个测试API"
    base_url = "https://httpbin.org"
    method = "GET"
    path = "/get"
    headers = @{}
    body_schema = @{}
    auth_type = "none"
    timeout_ms = 30000
    enabled = $true
} | ConvertTo-Json -Depth 10
Write-Host "Request:"
$apiJson
Write-Host ""
$apiResp = Invoke-RestMethod -Uri "$baseUrl/api-catalog/" -Method Post -Body ([System.Text.Encoding]::UTF8.GetBytes($apiJson)) -ContentType "application/json"
Write-Host "API ID: $($apiResp.id)" -ForegroundColor Green
$apiId = $apiResp.id

# Step 2: Create chain
Write-Host "`n=== Step 2: 创建链 ===" -ForegroundColor Cyan
$chainJson = @{
    name = "Hello World Chain"
    description = "第一个测试链"
    members = @(
        @{
            order = 1
            api_id = $apiId
            input_mapping = @{
                url = "url"
            }
            output_mapping = @{
                result = "result"
            }
        }
    )
} | ConvertTo-Json -Depth 10
Write-Host "Request:"
$chainJson
Write-Host ""
$chainResp = Invoke-RestMethod -Uri "$baseUrl/api-catalog/chains" -Method Post -Body ([System.Text.Encoding]::UTF8.GetBytes($chainJson)) -ContentType "application/json"
Write-Host "Chain ID: $($chainResp.id)" -ForegroundColor Green
$chainId = $chainResp.id

# Step 3: Execute chain
Write-Host "`n=== Step 3: 执行链 ===" -ForegroundColor Cyan
$execJson = @{
    input_data = @{
        url = "https://httpbin.org/get?hello=world"
    }
} | ConvertTo-Json
Write-Host "Request:"
$execJson
Write-Host ""
$execResp = Invoke-RestMethod -Uri "$baseUrl/api-catalog/chains/$chainId/execute" -Method Post -Body ([System.Text.Encoding]::UTF8.GetBytes($execJson)) -ContentType "application/json"
Write-Host "执行结果:" -ForegroundColor Yellow
$execResp | ConvertTo-Json | Write-Host
