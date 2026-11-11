param([ValidateSet('Debug','Release')][string]$Configuration='Release', [string]$DefaultServerUrl='')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$buildCache=Join-Path $env:LOCALAPPDATA 'TelegramAgent-build'
if(-not $env:JAVA_HOME){
    $env:JAVA_HOME=(Get-ChildItem -LiteralPath (Join-Path $buildCache 'jdk') -Directory | Select-Object -First 1).FullName
}
if(-not $env:ANDROID_HOME){$env:ANDROID_HOME=Join-Path $buildCache 'android-sdk'}
if(-not (Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin\java.exe'))){throw 'JDK 17 yoki undan yangi JDK kerak.'}
$env:PATH=(Join-Path $env:JAVA_HOME 'bin')+';'+$env:PATH
$env:GRADLE_USER_HOME=Join-Path $buildCache 'gradle-cache'
$env:TELEGRAM_AGENT_DEFAULT_URL=$DefaultServerUrl
$gradlePath=Join-Path $buildCache 'gradle\gradle-8.9\bin\gradle.bat'
if(-not (Test-Path -LiteralPath $gradlePath)){throw 'Gradle 8.9 ni Android Studio yoki rasmiy distributiv orqali tayyorlang.'}
$testClasses=Join-Path $buildCache 'address-tests'
New-Item -ItemType Directory -Path $testClasses -Force | Out-Null
& (Join-Path $env:JAVA_HOME 'bin\javac.exe') -d $testClasses (Join-Path $PSScriptRoot 'app\src\main\java\uz\telegramagent\mobile\ServerAddress.java') (Join-Path $PSScriptRoot 'tests\ServerAddressTest.java')
if($LASTEXITCODE -ne 0){throw 'Android address tests did not compile.'}
& (Join-Path $env:JAVA_HOME 'bin\java.exe') -cp $testClasses uz.telegramagent.mobile.ServerAddressTest
if($LASTEXITCODE -ne 0){throw 'Android address tests failed.'}
if($Configuration -eq 'Release'){
    $signingPath=Join-Path $projectRoot 'data\android-signing.json'
    $keyPath=Join-Path $projectRoot 'data\android-release.p12'
    if(-not (Test-Path -LiteralPath $signingPath)){
        if(Test-Path -LiteralPath $keyPath){throw 'APK imzo kaliti bor, uning sozlama faylini tiklang.'}
        $keyBytes=New-Object byte[] 36
        $keyGenerator=[Security.Cryptography.RandomNumberGenerator]::Create()
        $keyGenerator.GetBytes($keyBytes)
        $keyGenerator.Dispose()
        $keyPassword=[Convert]::ToBase64String($keyBytes)
        @{password=$keyPassword} | ConvertTo-Json | Set-Content -LiteralPath $signingPath -Encoding utf8
    }
    $signing=Get-Content -LiteralPath $signingPath -Raw | ConvertFrom-Json
    $env:TELEGRAM_AGENT_STORE_PASSWORD=$signing.password
    $env:TELEGRAM_AGENT_KEYSTORE=$keyPath
    if(-not (Test-Path -LiteralPath $keyPath)){
        & (Join-Path $env:JAVA_HOME 'bin\keytool.exe') -genkeypair -keystore $keyPath -storetype PKCS12 -storepass:env TELEGRAM_AGENT_STORE_PASSWORD -keypass:env TELEGRAM_AGENT_STORE_PASSWORD -alias telegram-agent -keyalg RSA -keysize 3072 -validity 10000 -dname 'CN=TelegramAgent'
        if($LASTEXITCODE -ne 0){throw 'APK imzo kaliti yaratilmagan.'}
    }
}
try {
    & $gradlePath -p $PSScriptRoot --console=plain "assemble$Configuration"
    if($LASTEXITCODE -ne 0){throw 'Android APK build failed.'}
    $variant=$Configuration.ToLowerInvariant()
    $source=Join-Path $PSScriptRoot "app\build\outputs\apk\$variant\app-$variant.apk"
    $target=Join-Path $projectRoot 'data\downloads'
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    $apkPath=Join-Path $target 'TelegramAgent.apk'
    Copy-Item -LiteralPath $source -Destination $apkPath -Force
    $buildTools=Get-ChildItem -LiteralPath (Join-Path $env:ANDROID_HOME 'build-tools') -Directory | Sort-Object Name -Descending | Where-Object {Test-Path -LiteralPath (Join-Path $_.FullName 'apksigner.bat')} | Select-Object -First 1
    if(-not $buildTools){throw 'Android apksigner tool not found.'}
    & (Join-Path $buildTools.FullName 'apksigner.bat') verify --verbose $apkPath
    if($LASTEXITCODE -ne 0){throw 'APK signature check failed.'}
    Write-Host "APK tayyor: $apkPath"
} finally {
    Remove-Item Env:TELEGRAM_AGENT_STORE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:TELEGRAM_AGENT_KEYSTORE -ErrorAction SilentlyContinue
    Remove-Item Env:TELEGRAM_AGENT_DEFAULT_URL -ErrorAction SilentlyContinue
}
