{{- define "unoarena-placeholder-lib.deployment" -}}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "unoarena-placeholder-lib.name" . }}
  labels:
{{ include "unoarena-placeholder-lib.labels" . | indent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
{{ include "unoarena-placeholder-lib.selectorLabels" . | indent 6 }}
  template:
    metadata:
      labels:
{{ include "unoarena-placeholder-lib.selectorLabels" . | indent 8 }}
        unoarena.itba/context: {{ .Values.context | quote }}
    spec:
      containers:
        - name: {{ include "unoarena-placeholder-lib.name" . }}
          image: "{{ .Values.image.repository }}{{- if .Values.image.digest }}@{{ .Values.image.digest }}{{- else }}:{{ .Values.image.tag }}{{- end }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: {{ .Values.containerPort }}
          env:
            - name: SERVICE_NAME
              value: {{ .Values.serviceName | quote }}
{{- range $key, $value := .Values.env }}
            - name: {{ $key | quote }}
              value: {{ $value | quote }}
{{- end }}
          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 3
            periodSeconds: 5
            failureThreshold: 6
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
            failureThreshold: 3
          resources:
{{ toYaml .Values.resources | indent 12 }}
{{- end -}}
