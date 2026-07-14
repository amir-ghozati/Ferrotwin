targetScope = 'resourceGroup'

param appName string
param environmentName string
param location string

@secure()
param postgresPassword string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: environmentName
}

resource postgres 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location

  properties: {
    managedEnvironmentId: env.id

    configuration: {
      ingress: {
        external: false
      }

      secrets: [
        {
          name: 'postgres-password'
          value: postgresPassword
        }
      ]
    }

    template: {
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
      volumes: [
        {
          name: 'postgres-data'
          storageType: 'AzureFile'
          storageName: 'postgres-storage'
          mountOptions: 'uid=999,gid=999,dir_mode=0750,file_mode=0750,nobrl,mfsymlinks,cache=none'
        }
      ]

      containers: [
        {
          name: 'postgres'
          image: 'postgres:16'

          env: [
            {
              name: 'POSTGRES_USER'
              value: 'ferrotwin'
            }
            {
              name: 'POSTGRES_PASSWORD'
              secretRef: 'postgres-password'
            }
            {
              name: 'POSTGRES_DB'
              value: 'ferrotwin'
            }
          ]

          volumeMounts: [
            {
              volumeName: 'postgres-data'
              mountPath: '/var/lib/postgresql/data'
            }
          ]

          resources: {
            cpu: '0.5'
            memory: '1Gi'
          }
        }
      ]
    }
  }
}
