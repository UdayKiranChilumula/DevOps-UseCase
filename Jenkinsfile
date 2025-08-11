pipeline {
    agent any

    environment {
        BACKEND_IMAGE = "udaykiranchilumula/aws-backend"
        FRONTEND_IMAGE = "udaykiranchilumula/aws-frontend"
    }

    stages {
        stage('Checkout') {
            steps {
                git branch: 'main', url: 'https://github.com/UdayKiranChilumula/DevOps-UseCase.git'
            }
        }

        stage('Build Backend Image') {
            steps {
                dir('backend') {
                    script {
                        sh """
                        docker build -t ${BACKEND_IMAGE}:latest .
                        """
                    }
                }
            }
        }

        stage('Build Frontend Image') {
            steps {
                dir('frontend') {
                    script {
                        sh """
                        docker build -t ${FRONTEND_IMAGE}:latest .
                        """
                    }
                }
            }
        }

        stage('Push Images') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'docker-hub-credentials', usernameVariable: 'DOCKERHUB_USERNAME', passwordVariable: 'DOCKERHUB_PASSWORD')]) {
                sh """
                echo "${DOCKERHUB_PASSWORD}" | docker login -u "${DOCKERHUB_USERNAME}" --password-stdin
                docker push ${BACKEND_IMAGE}:latest
                docker push ${FRONTEND_IMAGE}:latest
                """
            }
            }
        }


        stage('Deploy to Kubernetes') {
            steps {
                script {
                    sh """
                    kubectl apply -f k8s/postgres/configmap.yaml --validate=false
                    kubectl apply -f k8s/postgres/secret.yaml --validate=false
                    kubectl apply -f k8s/postgres/statefulset.yaml --validate=false
                    kubectl apply -f k8s/backend.yaml --validate=false
                    kubectl apply -f k8s/frontend.yaml --validate=false
                    kubectl apply -f k8s/cronjob.yaml --validate=false
                    """
                }
            }
        }
    }

    post {
        always {
            echo "Cleaning up cloned repo directory..."
            deleteDir() // Jenkins built-in — cleans the workspace
        }
    }

}
