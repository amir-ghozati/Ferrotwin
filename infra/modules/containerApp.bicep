targetScope = 'resourceGroup'

param appName string
param environmentName string
param location string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: environmentName
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location

  properties: {
    managedEnvironmentId: env.id

    configuration: {
      ingress: {
        external: true
        targetPort: 80
      }
    }

    template: {
      containers: [
        {
          name: 'inference'

          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

          resources: {
            cpu: '0.25'
            memory: '0.5Gi'
          }
        }
      ]
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
