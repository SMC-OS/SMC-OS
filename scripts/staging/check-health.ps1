param(
    [Parameter(Mandatory = $true)][string]$WebOrigin,
    [Parameter(Mandatory = $true)][string]$ApiOrigin
)

$ErrorActionPreference = "Stop"
foreach ($origin in @($WebOrigin, $ApiOrigin)) {
    $uri = [Uri]$origin
    if ($uri.Scheme -ne "https" -or $uri.Host -in @("localhost", "127.0.0.1", "::1") -or $uri.AbsolutePath -ne "/" -or $uri.UserInfo -or $uri.Query -or $uri.Fragment) {
        throw "Origins must be public HTTPS origins without paths."
    }
}

$web = Invoke-WebRequest -Uri $WebOrigin -UseBasicParsing
if ($web.StatusCode -lt 200 -or $web.StatusCode -ge 400) { throw "Web endpoint failed." }
foreach ($check in @(@{ Path="/health"; Body='{"status":"healthy"}' }, @{ Path="/ready"; Body='{"status":"ready","database":"reachable"}' })) {
    $response = Invoke-WebRequest -Uri ($ApiOrigin.TrimEnd("/") + $check.Path) -UseBasicParsing
    if ($response.StatusCode -ne 200 -or $response.Content -ne $check.Body -or -not $response.Headers["X-Request-ID"]) { throw "API health contract failed." }
}
Write-Output "Staging public health checks passed."
