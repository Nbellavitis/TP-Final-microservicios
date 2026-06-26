{{- define "unoarena-placeholder-lib.service" -}}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "unoarena-placeholder-lib.name" . }}
  labels:
{{ include "unoarena-placeholder-lib.labels" . | indent 4 }}
spec:
  type: {{ .Values.service.type }}
  selector:
{{ include "unoarena-placeholder-lib.selectorLabels" . | indent 4 }}
  ports:
    - name: http
      port: {{ .Values.service.port }}
      targetPort: http
{{- end -}}
