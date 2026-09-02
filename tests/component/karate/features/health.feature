Feature: Health Check API

 Background:
 * def contextPath = '/cccodr'
 * def baseUrl = urlBase + contextPath + '/health'

 Scenario: Health check endpoint returns healthy status
 Given url baseUrl
 When method get
 Then status 200
 And match response.status == 'healthy'
 And match response.service == 'contract-compliance-check-orchestrator-cccodr'