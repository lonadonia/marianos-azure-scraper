// marianos-azure-headless on Azure Container Apps Jobs.
//
// Creates, in the target resource group:
//   * a user-assigned managed identity for this collector only;
//   * its role assignments: AcrPull (image), Key Vault Secrets User (the Scrapfly key and the database URL),
//     Storage Blob Data Contributor (this collector's own blob container);
//   * one scheduled job per store (cron in UTC; the collector acts only on the store-local occurrence);
//   * one manual job for operations (db-upgrade, status, resume, stop, finalize, export, release-hold ...);
//   * optionally a Container Apps environment with a Log Analytics workspace (createEnvironment = true).
//
// It does not create the container registry, the Key Vault, the storage account or the PostgreSQL server:
// they are named by parameters (existing resources, possibly shared with other workloads). Nothing in this
// file holds a secret value. Deploy: azure/deploy.sh (see docs/AZURE.md).

targetScope = 'resourceGroup'

@description('Location of the new resources.')
param location string = resourceGroup().location

@description('Prefix of the resource names (identity, jobs).')
@maxLength(24)
param namePrefix string = 'marianos-collector'

@description('Image, e.g. myregistry.azurecr.io/marianos-collector:1.2.1')
param image string

@description('Name of the existing Azure Container Registry holding the image (same resource group).')
param acrName string

@description('Name of the existing Key Vault (same resource group) holding the secrets below.')
param keyVaultName string

@description('Key Vault secret holding the Scrapfly API key.')
param scrapflyKeySecretName string = 'marianos-collector-scrapfly-api-key'

@description('Key Vault secret holding the PostgreSQL URL (postgresql://user:password@host:5432/db?sslmode=require). With databaseAuth = entra, the URL without a password.')
param databaseUrlSecretName string = 'marianos-collector-database-url'

@description('password: the password is in the URL secret. entra: Microsoft Entra authentication with this job identity (no password).')
@allowed([
  'password'
  'entra'
])
param databaseAuth string = 'password'

@description('Name of the existing storage account (same resource group).')
param storageAccountName string

@description('Blob container of this collector (runs, exports, the published dataset). Created when missing.')
param blobContainerName string = 'marianos-collector'

@description('One scheduled job per store: storeKey (config/stores.yaml), cronUtc (marianos-collector schedule-info: cron_utc_with_continuation, every 30 minutes, so an unfinished run is continued; each firing exits in seconds when there is nothing to start or continue) and jobName (2-32 lowercase letters, digits and hyphens, unique in the resource group).')
param schedules array = [
  {
    storeKey: 'marianos-53100503-instore'
    cronUtc: '*/30 * * * *'
    jobName: 'marianos-53100503-instore'
  }
]

@description('Maximum duration of one execution, in seconds. Keep it above the collection max_segment_minutes (one execution); the whole run spans several executions.')
param replicaTimeoutSeconds int = 21600

@description('Platform retries of a failed execution. The collector retries pages and transient stops itself.')
@minValue(0)
@maxValue(3)
param replicaRetryLimit int = 1

param cpu string = '0.5'
param memory string = '1Gi'

@description('Create a Container Apps environment and a Log Analytics workspace (false: use environmentId).')
param createEnvironment bool = false

@description('Existing Container Apps environment resource id (when createEnvironment is false).')
param environmentId string = ''

@description('Log retention of a new Log Analytics workspace, in days.')
param logRetentionDays int = 30

var roleAcrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var roleKeyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var roleBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storage
  name: 'default'
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: blobContainerName
  properties: {
    publicAccess: 'None'
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-identity'
  location: location
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, roleAcrPull)
  scope: acr
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAcrPull)
  }
}

resource secretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, identity.id, roleKeyVaultSecretsUser)
  scope: vault
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultSecretsUser)
  }
}

resource blobWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(container.id, identity.id, roleBlobDataContributor)
  scope: container
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleBlobDataContributor)
  }
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = if (createEnvironment) {
  name: '${namePrefix}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: logRetentionDays
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = if (createEnvironment) {
  name: '${namePrefix}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace!.properties.customerId
        sharedKey: workspace!.listKeys().primarySharedKey
      }
    }
  }
}

var envId = createEnvironment ? environment!.id : environmentId
var vaultUri = vault.properties.vaultUri

var secrets = [
  {
    name: 'scrapfly-api-key'
    keyVaultUrl: '${vaultUri}secrets/${scrapflyKeySecretName}'
    identity: identity.id
  }
  {
    name: 'database-url'
    keyVaultUrl: '${vaultUri}secrets/${databaseUrlSecretName}'
    identity: identity.id
  }
]

var environmentVariables = [
  {
    name: 'SCRAPFLY_API_KEY'
    secretRef: 'scrapfly-api-key'
  }
  {
    name: 'MARIANOS_COLLECTOR_DATABASE_URL'
    secretRef: 'database-url'
  }
  {
    name: 'MARIANOS_COLLECTOR_DATABASE_AUTH'
    value: databaseAuth
  }
  {
    name: 'MARIANOS_COLLECTOR_STORAGE'
    value: 'azure_blob'
  }
  {
    name: 'MARIANOS_COLLECTOR_BLOB_ACCOUNT_URL'
    value: storage.properties.primaryEndpoints.blob
  }
  {
    name: 'MARIANOS_COLLECTOR_BLOB_CONTAINER'
    value: blobContainerName
  }
  {
    // DefaultAzureCredential picks this user-assigned identity (Blob storage and Entra database tokens).
    name: 'AZURE_CLIENT_ID'
    value: identity.properties.clientId
  }
  {
    name: 'MARIANOS_COLLECTOR_ACTOR'
    value: 'azure-job'
  }
]

var registries = [
  {
    server: acr.properties.loginServer
    identity: identity.id
  }
]

resource scheduled 'Microsoft.App/jobs@2024-03-01' = [
  for s in schedules: {
    name: s.jobName
    location: location
    identity: {
      type: 'UserAssigned'
      userAssignedIdentities: {
        '${identity.id}': {}
      }
    }
    properties: {
      environmentId: envId
      configuration: {
        triggerType: 'Schedule'
        replicaTimeout: replicaTimeoutSeconds
        replicaRetryLimit: replicaRetryLimit
        scheduleTriggerConfig: {
          cronExpression: s.cronUtc
          parallelism: 1
          replicaCompletionCount: 1
        }
        secrets: secrets
        registries: registries
      }
      template: {
        containers: [
          {
            name: 'collector'
            image: image
            args: [
              'run'
              '--store'
              s.storeKey
              '--scheduled'
            ]
            env: environmentVariables
            resources: {
              cpu: json(cpu)
              memory: memory
            }
          }
        ]
      }
    }
    dependsOn: [
      acrPull
      secretsUser
      blobWriter
    ]
  }
]

resource ops 'Microsoft.App/jobs@2024-03-01' = {
  name: take('${namePrefix}-ops', 32)
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: envId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: replicaTimeoutSeconds
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      secrets: secrets
      registries: registries
    }
    template: {
      containers: [
        {
          name: 'collector'
          image: image
          // The operator writes the command in MARIANOS_COLLECTOR_COMMAND, then starts this job (docs/AZURE.md).
          args: [
            'ops'
          ]
          env: concat(environmentVariables, [
            {
              name: 'MARIANOS_COLLECTOR_COMMAND'
              value: 'status'
            }
          ])
          resources: {
            cpu: json(cpu)
            memory: memory
          }
        }
      ]
    }
  }
  dependsOn: [
    acrPull
    secretsUser
    blobWriter
  ]
}

output identityClientId string = identity.properties.clientId
output identityPrincipalId string = identity.properties.principalId
output identityName string = identity.name
output scheduledJobs array = [for (s, i) in schedules: scheduled[i].name]
output opsJob string = ops.name
